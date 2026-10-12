"""A world is carried to another binary, never wiped (docs/FOUNDATION.md §2; docs/OVERHAUL.md section 5 step 1):
`delvetalk-obend carry` reads the world from the snapshot at its journal's head and writes a new journal whose `carried`
genesis cites the old head, holding the whole store, the suspensions, the standing indexes and the old chain's
entries by hash; `python3 -m transport carry` carries a state directory and checks the result.

Evidence for FOUNDATION §2 (layer: host). Refuted by an object whose state CID moves, an old receipt
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
        commonplace(self, doors=[("GARDEN", "garden", [])])
        asked = self.host.send(op="world-turn", principal="glm", object="commonplace", method="receive", identity="prose",
                               argument=record(text=label("Could we plant a silver fern that remembers?"), post=label("at://x/p/2")), reach="mention")
        self.assertEqual(asked["status"], "suspended", asked)  # words at the commonplace: hob is asked
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

    def test_a_retry_after_the_carry_answers_the_receipt_and_repeats_nothing(self):
        # codex 2026-10-12 host 8: the carry kept no identity, so a retried plant planted a second bell.
        old = {e["identity"]["intent"]: e for e in journal_entries(self.path) if e.get("identity", {}).get("principal") == "glm"}
        p, out = self.carry()
        self.assertEqual(p.returncode, 0, p.stderr)
        [genesis] = journal_entries(out)
        self.assertIn("planted", [r["identity"]["intent"] for r in genesis["outcome"]["identities"]])
        new = self.opened(out)
        for generation in range(2):
            again = self.plant("glm", "planted", new)
            self.assertEqual((again["status"], again["receipt"]["hash"]), ("admitted", old["planted"]["hash"]), again)
            self.assertEqual(self.children(new), ["garden/bell/1"])
            other = new.send(op="world-turn", principal="glm", object="garden", method="receive", identity="planted",
                             argument=record(text=label("delvetalk garden plant\ncolour: amber\nseed: moths"), post=label("at://x/p/q")))
            self.assertEqual(other.get("class"), "duplicateIdentity", other)
            seen = new.send(op="world-receipt", principal="glm", identity="planted")
            self.assertEqual((seen["status"], seen["receipt"]["hash"]), ("receipt", old["planted"]["hash"]), seen)
            if generation == 0:
                # Carried again, the bindings the first carry kept are kept.
                self.assertEqual(new.send(op="world-snapshot")["status"], "snapshot")
                new.close()
                again_out = os.path.join(self.dir.name, "again.journal")
                q = subprocess.run([binary(), "carry", "--from", out, "--out", again_out, "--reason", "again"],
                                   capture_output=True, text=True, timeout=600)
                self.assertEqual(q.returncode, 0, q.stderr)
                new = self.opened(again_out)
        new.close()

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
TALLY_NOTED_SOURCE = """edition ObjectiveBend 1
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
"""
TALLY_NOTED = declared(TALLY_NOTED_SOURCE, "bump", "jot")
# A package that declares its law (`objects/Counted.obend`), as one host shipped it.
COUNTED_SOURCE = TALLY_SOURCE.replace("def initial()", 'law counted "the count only rises": monotone(count)\ndef initial()', 1)


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
        self.ship(declared(COUNTED_SOURCE), "Counted")
        for name in ("l", "m"):
            r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                               modules=[{"name": "Counted", "source": declared(COUNTED_SOURCE)}], entry="initial", seed=record())
            self.assertEqual(r["status"], "created", r)
        self.make("c", PACKAGE, source_seed())  # a package the image does not ship: it keeps its pin
        for obj in ("t", "t", "u", "c"):
            self.assertEqual(self.turn(obj, "bump")["status"], "admitted")
        self.before = {i: self.host.send(op="world-object", principal="ember", object=i)["record"] for i in ("t", "u", "c")}

    def ship(self, source, name="Tally"):
        with open(os.path.join(self.image, "objects", name + ".obend"), "w", encoding="utf-8") as f:
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

    def test_a_moved_object_whose_package_offers_carried_is_told_once_and_starts_again_from_there(self):
        # As a kind tells what it makes `made`, the carry tells what it moved `carried`: the tide's re-arm.
        self.ship(declared(TALLY_NOTED_SOURCE.replace(
            "def bump(", "def carried(state: State, input: {}, context: Abi.Context) -> Activity<Nat>:\n  add(context, 1000n)\ndef bump(", 1),
            "bump", "jot", "~carried"))
        p, out = self.carry()
        self.assertEqual(p.returncode, 0, p.stderr)
        carried = json.loads(p.stdout)
        self.assertEqual(carried["rearmed"], ["t", "u"], carried)  # c did not move: its suspensions, if any, stand
        [genesis] = journal_entries(out)
        told = [d for d in genesis["outcome"]["pending"] if d["method"] == "carried"]
        self.assertEqual(sorted((d["to"], d["id"], d["sender"]) for d in told), [("t", "carried:t", ""), ("u", "carried:u", "")])
        new = self.opened(out)
        self.assertEqual(new.send(op="world-advance", principal="ember", height=1)["status"], "advanced")
        count = lambda i: field(new.send(op="world-view", principal="ember", object=i)["state"], "count")["value"]
        self.assertEqual((count("t"), count("u")), ("1002", "1010"))
        # Once: a reopen replays the turns it ran, and a second advance tells nobody again.
        new.close()
        self.hosts.remove(new)
        again = self.opened(out)
        self.assertEqual(again.send(op="world-advance", principal="ember", height=2)["status"], "advanced")
        self.assertEqual(field(again.send(op="world-view", principal="ember", object="t")["state"], "count")["value"], "1002")

    def test_a_moved_object_takes_its_packages_new_law_and_an_amended_one_is_kept_and_named(self):
        version = self.host.send(op="world-view", principal="ember", object="m")["version"]
        amended = 'law counted: monotone(count)\nlaw mine "ember alone bumps": request.subject == "ember"'
        a = self.host.send(op="world-amend", principal="ember", identity="am-m", object="m", version=version, law=amended)
        self.assertEqual(a["status"], "admitted", a)
        was = self.host.send(op="world-object", principal="ember", object="l")["record"]["law"]
        now = 'law counted "the count only rises, and anyone places rules on it": monotone(count) or request.kind == rule'
        self.ship(declared(COUNTED_SOURCE.replace('law counted "the count only rises": monotone(count)', now)), "Counted")
        p, out = self.carry()
        self.assertEqual(p.returncode, 0, p.stderr)
        carried = json.loads(p.stdout)
        moved = {m["object"]: m for m in carried["moved"]}
        self.assertEqual((sorted(moved), moved["l"]["law"]["before"], "law" in moved["m"]), (["l", "m"], was, False), carried)
        self.assertEqual(moved["l"]["law"]["after"], "law counted: (monotone(count)) or (request.kind == 4)")
        self.assertEqual([k["object"] for k in carried["kept"]], ["m"])
        self.assertIn("ember alone bumps", carried["kept"][0]["law"])
        new = self.opened(out)
        law = lambda i: new.send(op="world-object", principal="ember", object=i)["record"]
        self.assertEqual((law("l")["law"], law("m")["law"]), (moved["l"]["law"]["after"], carried["kept"][0]["law"]))
        # The new law's own reading is the one a refusal by it reads.
        self.assertEqual(law("l")["readings"], [{"name": "counted", "reading": "the count only rises, and anyone places rules on it"}])

    def test_a_moved_object_holding_its_packages_law_takes_the_packages_new_rule_and_want_lines(self):
        version = self.host.send(op="world-view", principal="ember", object="m")["version"]
        a = self.host.send(op="world-amend", principal="ember", identity="am-m", object="m", version=version,
                           law='law counted: monotone(count)\nlaw mine "ember alone bumps": request.subject == "ember"')
        self.assertEqual(a["status"], "admitted", a)
        low = 'want low "a count under ten": new.count <= 9 asks delvetalk {request.object} bump'
        self.ship(declared(COUNTED_SOURCE.replace("def initial()", low + "\ndef initial()", 1)), "Counted")
        p, out = self.carry()
        self.assertEqual(p.returncode, 0, p.stderr)
        moved = {m["object"]: m for m in json.loads(p.stdout)["moved"]}
        self.assertEqual((moved["l"].get("placed"), moved["m"].get("placed")), (["low"], None), moved)
        new = self.opened(out)
        wants = lambda i: [r["name"] for r in new.send(op="world-wants", principal="ember", object=i)["rows"]]
        self.assertEqual((wants("l"), wants("m")), (["low"], []))

    def test_a_refused_moves_whole_refusal_is_printed_and_its_clause_reads_within_its_bound(self):
        self.ship(TALLY_NOTED.replace("  note: String", "  note: Nowhere", 1))  # a type nothing declares
        p, out = self.carry()
        self.assertEqual(p.returncode, 0, p.stderr)
        left = {x["object"]: x["reading"] for x in json.loads(p.stdout)["left"]}
        self.assertIn("t", left, p.stdout)
        self.assertTrue(left["t"].startswith("left at the carry: its package does not compile"), left)
        self.assertGreater(len(left["t"].encode()), 200)
        readings = self.opened(out).send(op="world-object", principal="ember", object="t")["record"]["readings"]
        clause = next(r["reading"] for r in readings if r["name"] == "retired")
        # The clause's reading is the refusal's first line, its quotes made plain, within a reading's 200 bytes.
        self.assertTrue(left["t"].replace('"', "'").startswith(clause.removesuffix("...")) and len(clause.encode()) <= 200, clause)

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
        with open(os.path.join(old, "delvetalk.toml"), "w") as f:  # the old front's port; the new state names its own
            f.write("http_port = 8765\n")
        os.makedirs(new)
        with open(os.path.join(new, "delvetalk.toml"), "w") as f:
            f.write("http_port = 18775\n")
        code = transport.main(["carry", "--from", old, "--to", new, "--reason", "the overhaul host", "--obend", binary()], out=out)
        lines = out.getvalue().splitlines()
        self.assertEqual(code, 0, lines)
        report = json.loads(lines[0])
        self.assertEqual((report["check"]["problems"], report["check"]["rendered"], report["check"]["objects"]),
                         ([], report["objects"], report["objects"]), report)
        self.assertEqual(report["check"]["receipts"], report["height"])
        # Genesis's laws and kinds refreshed after the check: a town begun by this image already holds them.
        refreshed = [json.loads(line)["refresh"] for line in lines[1:-1]]
        self.assertEqual({r["status"] for r in refreshed}, {"current"}, refreshed)
        self.assertRegex(lines[-1], r"^hob: the world was carried to a newer host at entry \d+; everything is where it was, and the carry is receipt [a-z]{5}-[a-z]{5}\.$")
        with open(os.path.join(new, "worlds", "town", "publications.after")) as f:
            self.assertEqual(f.read().strip(), "1")
        with open(os.path.join(new, "worlds", "town", "awaiting", "x.json")) as f:
            self.assertEqual(json.load(f)["height"], 1)
        self.assertFalse(os.path.exists(os.path.join(new, "journal.lock")))
        with open(os.path.join(new, "delvetalk.toml")) as f:
            self.assertEqual(f.read(), "http_port = 18775\n")  # the configuration the carry was run under stands
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
