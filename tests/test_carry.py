"""A world is carried to another binary, never wiped (docs/TENURE.md section 1; docs/OVERHAUL.md section 5 step 1):
`delvetalk-obend carry` reads the world from the snapshot at its journal's head and writes a new journal whose `carried`
genesis cites the old head, holding the whole store, the suspensions, the standing indexes and the old chain's
entries by hash; `python3 -m transport carry` carries a state directory and checks the result.

Evidence for TENURE section 1(b) (layer: host). Refuted by an object whose state CID moves, an old receipt
that no longer resolves by its slug, a carried world that takes no new turn or loses a suspension, a carry that runs
without a snapshot at the head, over an open journal or into an existing one, an object left that is not retired, or
a journal of another edition that neither opens nor carries, or a package the image changed whose objects keep the
code before, lose their state in the move, carry a state their new package does not hold, or a move that refuses
stopping the carry rather than leaving its object retired.

    python3 -W error -m unittest tests.test_carry -v
"""
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tests import test_policy
from tests.host import Host, binary, served
from tests.test_chain import town_garden
from tests.test_receive import commonplace
from tests.bend import declared
from tests.test_extend import LAYER
from tests.test_reflection import PACKAGE, WORLD_LIBRARY, Reflection, source_seed
from tests.test_snapshot import read_snapshot, write_snapshot
from tests.wire import cid_of, field, label, nat, record, rows, write_journal
from transport.config import LIBRARY
from transport.identity import slug
from transport.journal import entries as journal_entries

PLANT = "delvetalk garden plant\nseed: a fern that remembers\ncolour: silver"


class Carry(Reflection):
    policy = test_policy.PolicyObject.policy

    def setUp(self):
        super().setUp()
        self.open_library()
        town_garden(self.host.send)
        self.make("c", PACKAGE, source_seed())
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(self.plant("glm", "planted")["status"], "admitted")

    def plant(self, who, identity, host=None):
        return (host or self.host).send(op="world-turn", principal=who, object="garden", method="receive", identity=identity,
                                        argument=record(text=label(PLANT), post=label("at://x/p/" + identity)), reach="mention")

    def children(self, host):
        state = host.send(op="world-view", principal="ember", object="garden")["state"]
        return [field(c, "object")["value"] for c in rows(field(state, "things"))]

    def objects(self, host):
        ids = host.send(op="world-objects", principal="ember")["ids"]
        return {i: host.send(op="world-object", principal="ember", object=i)["record"]["stateCid"] for i in ids}

    def carry(self, *argv, snapshot=True, out=None):
        """Snapshot the head, let go of the journal, and carry it: (process, out path)."""
        if snapshot:
            self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.release()
        out = out or os.path.join(self.dir.name, "carried.journal")
        p = subprocess.run([binary(), "carry", "--from", self.path, "--out", out, "--reason", "a newer host", *argv],
                           capture_output=True, text=True, timeout=600)
        return p, out

    def opened(self, path):
        h = self.spawn()
        got = h.send(op="world-open", path=path, verify=True)
        self.assertEqual((got["status"], got["snapshot"]["refused"]), ("opened", []), got)
        return h

    def test_every_object_and_receipt_crosses_and_the_world_goes_on(self):
        self.policy()
        commonplace(self, "policy", doors=[("GARDEN", "garden", [])])
        asked = self.host.send(op="world-turn", principal="glm", object="garden", method="receive", identity="prose",
                               argument=record(text=label("Could we plant a silver fern that remembers?"), post=label("at://x/p/2")), reach="mention")
        self.assertEqual([d["status"] for d in asked["delivered"]], ["suspended"], asked)
        before, old = self.objects(self.host), journal_entries(self.path)
        p, out = self.carry()
        self.assertEqual(p.returncode, 0, p.stderr)
        carried = json.loads(p.stdout)
        self.assertEqual((carried["status"], carried["carriedFrom"]["height"], carried["carriedFrom"]["cid"], carried["suspended"]),
                         ("carried", len(old), old[-1]["hash"], 1), carried)
        [genesis] = journal_entries(out)
        self.assertEqual((genesis["outcome"]["tag"], genesis["previous"], genesis["height"]), ("carried", old[-1]["hash"], 1))
        new = self.opened(out)
        status = new.send(op="world-status")
        self.assertEqual(status["carriedFrom"], {"world": self.path, "height": len(old), "cid": old[-1]["hash"],
                                                 "replay": old[0]["replay"], "reason": "a newer host"}, status)
        # Every object at the state it had; every receipt of the world before by its slug.
        self.assertEqual(self.objects(new), before)
        for e in old:
            got = new.send(op="world-resolve", principal="ember", slug=slug(e["hash"]))
            self.assertEqual((got["status"], got["kind"], got["cid"], got["carried"]["height"]), ("resolved", "receipt", e["hash"], e["height"]), got)
        # The carried suspension settles, and a resident's spell on a carried thing admits.
        [pending] = new.send(op="world-interpretations")["pending"]
        settled = new.send(op="world-interpretation", id=pending["id"],
                           reply={"status": "replied", "json": None, "model": "m",
                                  "raw": "delvetalk garden plant / colour: silver / seed: a fern that remembers"})
        self.assertEqual([r["status"] for r in settled["resumed"]], ["admitted"], settled)
        self.assertEqual(self.plant("kim", "after", new)["status"], "admitted")
        self.assertEqual(self.children(new), ["garden/bell/1", "garden/bell/2", "garden/bell/3"])
        # A fresh process replays the carried journal from its genesis to the same world.
        head = new.send(op="world-status")["head"]
        new.close()
        again = self.opened(out)
        self.assertEqual((again.send(op="world-status")["head"], self.children(again)), (head, ["garden/bell/1", "garden/bell/2", "garden/bell/3"]))

    def test_an_object_left_is_carried_retired_at_its_state(self):
        before = self.objects(self.host)
        p, out = self.carry("--leave", "c")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["left"], [{"object": "c", "reading": "left at the carry: a newer host"}])
        new = self.opened(out)
        self.assertEqual(self.objects(new), before)
        bumped = new.send(op="world-turn", principal="ember", object="c", method="bump", argument=record(), identity="after")
        self.assertEqual((bumped["status"], bumped["receipt"]["outcome"]["clause"]), ("refused", "retired"), bumped)
        self.assertEqual(self.plant("kim", "after", new)["status"], "admitted")

    def test_the_library_the_host_ships_is_sealed_and_the_old_pins_still_compile(self):
        before = self.objects(self.host)
        old = self.host.send(op="world-open", path=self.path)["library"]
        p, out = self.carry("--library", LIBRARY)
        self.assertEqual(p.returncode, 0, p.stderr)
        carried = json.loads(p.stdout)
        self.assertNotEqual(carried["library"], old)  # sealed as serve seals it: arrival's packages beside the library
        [genesis] = journal_entries(out)
        self.assertEqual(genesis["outcome"]["carriedFrom"]["library"], {"from": old, "to": carried["library"]})
        new = self.spawn()
        opened = new.send(op="world-open", path=out, verify=True, library=os.path.join(self.dir.name, "library"), principal="ember")
        self.assertEqual((opened["status"], opened["library"]), ("opened", carried["library"]), opened)
        self.assertEqual(self.objects(new), before)
        self.assertEqual(self.plant("kim", "after", new)["status"], "admitted")  # the garden's old pin compiles as before

    def test_a_carry_is_refused_by_name_without_its_snapshot_over_an_open_journal_or_into_a_journal(self):
        p, _ = self.carry(snapshot=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("has no snapshot at its head", p.stderr)
        self.assertIn("deploy/verify.sh --snapshot", p.stderr)
        held = self.spawn()
        self.assertEqual(held.send(op="world-open", path=self.path)["status"], "opened")
        self.assertEqual(held.send(op="world-snapshot")["status"], "snapshot")
        p = subprocess.run([binary(), "carry", "--from", self.path, "--out", os.path.join(self.dir.name, "x.journal"), "--reason", "r"],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 75, p.stderr)
        held.close()
        self.hosts.remove(held)
        p, out = self.carry(snapshot=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        p, _ = self.carry(snapshot=False, out=out)
        self.assertEqual(p.returncode, 1)
        self.assertIn("exists", p.stderr)
        p, _ = self.carry("--leave", "nobody", snapshot=False, out=os.path.join(self.dir.name, "y.journal"))
        self.assertEqual(p.returncode, 64)
        self.assertIn("holds no nobody", p.stderr)


class AnotherEdition(Reflection):
    """A journal written under another replay edition does not reopen here; it is carried."""

    def test_a_journal_of_another_edition_does_not_reopen_and_is_carried(self):
        self.open_library()
        self.make("c", PACKAGE, source_seed())
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        cid = self.host.send(op="world-object", principal="ember", object="c")["record"]["stateCid"]
        self.release()
        # The same world as a host of edition 7 wrote it: every entry sealed again, the snapshot's head with it.
        old, previous = journal_entries(self.path), "0" * 64
        for e in old:
            e.pop("hash")
            e["previous"] = previous
            if e["height"] == 1:
                e["replay"] = 7
            e["hash"] = previous = cid_of(e)
        os.remove(self.path)
        os.remove(self.path + ".blocks")
        write_journal(self.path, old)
        [snap] = [f for f in os.listdir(self.dir.name) if ".snapshot." in f]
        body = read_snapshot(os.path.join(self.dir.name, snap))
        body["head"] = old[-1]["hash"]
        write_snapshot(os.path.join(self.dir.name, snap), body)
        h = self.spawn()
        refused = h.send(op="world-open", path=self.path)
        self.assertEqual(refused["status"], "error")
        self.assertIn("journal replay edition 7", refused["message"])
        self.assertIn("carry it", refused["message"])
        h.close()
        self.hosts.remove(h)
        out = os.path.join(self.dir.name, "carried.journal")
        p = subprocess.run([binary(), "carry", "--from", self.path, "--out", out, "--reason", "edition 7 to this"],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["carriedFrom"]["replay"], 7)
        new = self.spawn()
        self.assertEqual(new.send(op="world-open", path=out, verify=True)["status"], "opened")
        self.assertEqual(new.send(op="world-object", principal="ember", object="c")["record"]["stateCid"], cid)
        self.assertEqual(new.send(op="world-turn", principal="ember", object="c", method="bump", argument=record(), identity="after")["status"], "admitted")


# A package the image ships (`objects/Tally.obend`), as one host shipped it and as the next ships it: the state gains
# `note`, and `migrate` reads the state as it was.
TALLY_SOURCE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def add(context: Abi.Context, n: Nat) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: n})})):
    case _: n
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  add(context, 1n)
"""
TALLY = declared(TALLY_SOURCE)
TALLY_NOTED = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
  note: String
record State1:
  count: Nat
def initial() -> State:
  {count: 0n, note: ""}
def migrate(old: State1) -> State:
  {count: old.count, note: "carried at {natText(old.count)}"}
def add(context: Abi.Context, n: Nat) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: n})})):
    case _: n
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  add(context, 1n)
def jot(state: State, input: {text: String}, context: Abi.Context) -> Activity<String>:
  match world.write(extend(keep(), {note: Plans.Edit::<String, {}>.set({value: input.text})})):
    case _: input.text
""", "bump", "jot")


class Moves(Reflection):
    """With `--library DIR`, an object whose package the image changed moves to it: compiled against the new library,
    its layers kept, its state converted by the package's `migrate` when it no longer conforms."""

    def setUp(self):
        super().setUp()
        self.image = os.path.join(self.dir.name, "image")
        shutil.copytree(WORLD_LIBRARY, os.path.join(self.image, "lib"))
        shutil.copytree(os.path.join(os.path.dirname(WORLD_LIBRARY), "objects"), os.path.join(self.image, "objects"))
        self.ship(TALLY)
        # A library module this image ships and the next does not (as Wake and Env went).
        self.fading = os.path.join(self.image, "lib", "Fading.obend")
        with open(self.fading, "w", encoding="utf-8") as f:
            f.write(TALLY)
        self.open_library(os.path.join(self.image, "lib"))
        for name in ("t", "u"):
            r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                               modules=[{"name": "Tally", "source": TALLY}], entry="initial", seed=record())
            self.assertEqual(r["status"], "created", r)
        layered = self.host.send(op="world-reprogram", principal="ember", identity="layer-u", object="u", version=0,
                                 package=LAYER, mode="extend")
        self.assertEqual(layered["status"], "admitted", layered)
        r = self.host.send(op="world-create", principal="ember", identity="mk-f", object="f",
                           modules=[{"name": "Fading", "source": TALLY}], entry="initial", seed=record())
        self.assertEqual(r["status"], "created", r)
        self.make("c", PACKAGE, source_seed())  # a package the image does not ship: it keeps its pin
        for obj in ("t", "t", "u", "c"):
            self.assertEqual(self.turn(obj, "bump")["status"], "admitted")
        self.before = {i: self.host.send(op="world-object", principal="ember", object=i)["record"] for i in ("t", "u", "c")}

    def ship(self, source):
        with open(os.path.join(self.image, "objects", "Tally.obend"), "w", encoding="utf-8") as f:
            f.write(source)

    def carry(self, *argv):
        if os.path.exists(self.fading):
            os.remove(self.fading)
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        self.release()
        out = os.path.join(self.dir.name, "carried.journal")
        p = subprocess.run([binary(), "carry", "--from", self.path, "--out", out, "--reason", "the image changed",
                            "--library", os.path.join(self.image, "lib"), *argv], capture_output=True, text=True, timeout=600)
        return p, out

    def opened(self, out):
        h = self.spawn()
        got = h.send(op="world-open", path=out, verify=True, library=os.path.join(self.dir.name, "library"), principal="ember")
        self.assertEqual((got["status"], got["snapshot"]["refused"]), ("opened", []), got)
        return h

    def test_a_changed_package_moves_its_objects_and_migrate_converts_their_state(self):
        self.ship(TALLY_NOTED)
        p, out = self.carry()
        self.assertEqual(p.returncode, 0, p.stderr)
        carried = json.loads(p.stdout)
        moved = {m["object"]: m for m in carried["moved"]}
        self.assertEqual(sorted(moved), ["t", "u"], carried)  # c's closure is the image's as it was
        # f's package is gone from the image: it is left, unnamed by the operator, saying why.
        self.assertEqual(carried["left"], [{"object": "f", "reading": "left at the carry: its package Fading is no longer shipped"}])
        for i in ("t", "u"):
            self.assertEqual((moved[i]["from"], moved[i]["migration"], moved[i]["before"]),
                             (self.before[i]["pin"], "migrate", self.before[i]["stateCid"]), moved[i])
            self.assertNotEqual(moved[i]["to"], moved[i]["from"])
        [genesis] = journal_entries(out)
        self.assertEqual(genesis["outcome"]["moved"], carried["moved"])
        new = self.opened(out)
        state = lambda i: new.send(op="world-view", principal="ember", object=i)
        t, u = state("t"), state("u")
        self.assertEqual((field(t["state"], "count")["value"], field(t["state"], "note")["value"]), ("2", "carried at 2"))
        self.assertEqual((field(u["state"], "count")["value"], field(u["state"], "note")["value"]), ("10", "carried at 10"))
        self.assertEqual(t["version"], self.before["t"]["version"] + 1)
        record_ = lambda i: new.send(op="world-object", principal="ember", object=i)["record"]
        self.assertEqual({i: record_(i)["pin"] for i in ("t", "u", "c")},
                         {"t": moved["t"]["to"], "u": moved["u"]["to"], "c": self.before["c"]["pin"]})
        self.assertEqual({i: record_(i)["stateCid"] for i in ("t", "u", "c")},
                         {"t": moved["t"]["after"], "u": moved["u"]["after"], "c": self.before["c"]["stateCid"]})
        # The new code runs, and the layer above it is still the one laid there.
        turn = lambda i, m, a: new.send(op="world-turn", principal="ember", object=i, method=m, argument=a, identity=f"after-{i}-{m}")
        self.assertEqual(turn("t", "jot", record(text=label("rung")))["status"], "admitted")
        self.assertEqual(turn("u", "bump", record())["status"], "admitted")
        self.assertEqual(turn("c", "bump", record())["status"], "admitted")
        self.assertEqual((field(state("t")["state"], "note")["value"], field(state("u")["state"], "count")["value"]), ("rung", "20"))
        head = new.send(op="world-status")["head"]
        new.close()
        self.hosts.remove(new)
        self.assertEqual(self.opened(out).send(op="world-status")["head"], head)

    def test_a_body_is_laid_again_as_the_first_layer_of_the_thing_it_names(self):
        body = os.path.join(self.image, "layer.obend")
        with open(body, "w", encoding="utf-8") as f:
            f.write(LAYER.replace("Super.add(context, 10n)", "Super.add(context, 100n)"))
        self.ship(TALLY_NOTED)
        p, out = self.carry("--body", "u=" + body)
        self.assertEqual(p.returncode, 0, p.stderr)
        carried = json.loads(p.stdout)
        moved = {m["object"]: m for m in carried["moved"]}
        self.assertEqual((moved.get("u", {}).get("body"), moved["t"].get("body")), (True, None), carried)
        new = self.opened(out)
        self.assertEqual(new.send(op="world-turn", principal="ember", object="u", method="bump", argument=record(), identity="b")["status"], "admitted")
        self.assertEqual(field(new.send(op="world-view", principal="ember", object="u")["state"], "count")["value"], "110")

    def test_a_package_that_changes_its_methods_alone_moves_with_its_state(self):
        self.ship(declared(TALLY_SOURCE + "def bump2(state: State, context: Abi.Context) -> Activity<Nat>:\n  add(context, 2n)\n"))
        p, out = self.carry()
        self.assertEqual(p.returncode, 0, p.stderr)
        moved = {m["object"]: m for m in json.loads(p.stdout)["moved"]}
        self.assertEqual({i: (m["migration"], m["after"]) for i, m in moved.items()},
                         {"t": ("", self.before["t"]["stateCid"]), "u": ("", self.before["u"]["stateCid"])})
        new = self.opened(out)
        self.assertEqual(new.send(op="world-turn", principal="ember", object="t", method="bump2", argument=record(), identity="b2")["status"], "admitted")

    def test_a_move_that_refuses_leaves_its_object_retired_at_its_old_pin_saying_why(self):
        self.ship(TALLY_NOTED.replace("def migrate(", "def unused(", 1))
        p, out = self.carry()
        self.assertEqual(p.returncode, 0, p.stderr)
        carried = json.loads(p.stdout)
        left = {x["object"]: x["reading"] for x in carried["left"]}
        self.assertEqual((carried["moved"], sorted(left)), ([], ["f", "t", "u"]))
        for i in ("t", "u"):
            self.assertEqual(left[i], "left at the carry: its state does not conform to its package's new state type, "
                                      "and the package defines no migrate; a migration is def migrate(old: OldState) -> State")
        new = self.opened(out)
        self.assertEqual({i: new.send(op="world-object", principal="ember", object=i)["record"]["stateCid"] for i in ("t", "u", "c")},
                         {i: self.before[i]["stateCid"] for i in ("t", "u", "c")})
        self.assertEqual(new.send(op="world-object", principal="ember", object="t")["record"]["pin"], self.before["t"]["pin"])
        bumped = new.send(op="world-turn", principal="ember", object="t", method="bump", argument=record(), identity="after")
        self.assertEqual((bumped["status"], bumped["receipt"]["outcome"]["clause"]), ("refused", "retired"), bumped)


class StateDirectory(unittest.TestCase):
    """`python3 -m transport carry` over a served town: the state directory moves, the cursors that named old heights
    are set to the genesis, the check passes, and serve opens the carried town and takes a turn."""

    def test_a_served_town_is_carried_with_its_transport_and_serves(self):
        from deploy import genesis
        from tests.town import Town
        from transport import __main__ as transport
        from transport.config import LIBRARY
        from transport.host import HostClient
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        town = Town(os.path.join(tmp.name, "v1"), cleanup=self.addCleanup)
        town.close()
        old = town.state
        os.makedirs(os.path.join(old, "worlds", "town", "awaiting"), exist_ok=True)
        with open(os.path.join(old, "worlds", "town", "publications.after"), "w") as f:
            f.write("70\n")
        with open(os.path.join(old, "worlds", "town", "awaiting", "x.json"), "w") as f:
            json.dump({"principal": "did:plc:x", "uri": "at://x/p/1", "height": 60}, f)
        # The snapshot at the head, by the binary of the journal's own edition (here, this one).
        h = Host()
        self.assertEqual(h.send(op="world-open", path=town.journal)["status"], "opened")
        self.assertEqual(h.send(op="world-snapshot")["status"], "snapshot")
        h.close()
        new, out = os.path.join(tmp.name, "v2", "state"), io.StringIO()
        code = transport.main(["carry", "--from", old, "--to", new, "--reason", "the overhaul host", "--obend", binary()], out=out)
        lines = out.getvalue().splitlines()
        self.assertEqual(code, 0, lines)
        report = json.loads(lines[0])
        self.assertEqual((report["check"]["problems"], report["check"]["rendered"], report["check"]["objects"]),
                         ([], report["objects"], report["objects"]), report)
        self.assertEqual(report["check"]["receipts"], report["height"])
        self.assertRegex(lines[-1], r"^hob: the world was carried to a newer host at entry \d+; everything is where it was, and the carry is receipt [a-z]{5}-[a-z]{5}\.$")
        with open(os.path.join(new, "worlds", "town", "publications.after")) as f:
            self.assertEqual(f.read().strip(), "1")
        with open(os.path.join(new, "worlds", "town", "awaiting", "x.json")) as f:
            self.assertEqual(json.load(f)["height"], 1)
        self.assertFalse(os.path.exists(os.path.join(new, "journal.lock")))
        server = served(new, cleanup=self.addCleanup, opener=genesis.OPENER, library=LIBRARY)
        root = HostClient(server.root)
        self.addCleanup(root.close)
        status = root.send({"op": "world-status"})
        self.assertEqual(status["carriedFrom"]["height"], report["height"], status)
        turned = root.send({"op": "world-turn", "principal": "did:plc:kim", "object": "garden", "method": "receive", "identity": "after",
                            "argument": record(text=label(PLANT), post=label("at://x/p/after")), "reach": "mention"})
        self.assertEqual(turned["status"], "admitted", turned)


if __name__ == "__main__":
    unittest.main()
