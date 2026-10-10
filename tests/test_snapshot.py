"""A snapshot every thousand entries lets a reopen replay only the tail; a tampered, foreign or
forged snapshot is refused by name and replay used instead.

Evidence for FOUNDATION §2 Journal (layer: host).

Snapshots: the store at a height in canonical bytes; world-open resumes from the newest valid
one and replays only later entries; one that fails a check is refused by name and the previous
one (or full replay) is used; `verify: true` replays everything and refuses a snapshot that
disagrees with replay at its height.

    python3 -W error -m unittest tests.test_snapshot -v
"""
import glob
import json
import os
import time
import unittest

from tests.test_chain import field
from tests.test_reflection import PACKAGE, Reflection, source_seed
from tests.wire import cbor, cbor_head, cid_of


def read_cbor(data, i=0):
    """The JSON subset the host writes: ints, text, arrays, maps, true/false/null."""
    ib = data[i]
    major, info = ib >> 5, ib & 31
    if major == 7:
        return {20: False, 21: True, 22: None}[info], i + 1
    i += 1
    if info < 24:
        n = info
    else:
        width = {24: 1, 25: 2, 26: 4, 27: 8}[info]
        n, i = int.from_bytes(data[i:i + width], "big"), i + width
    if major == 0:
        return n, i
    if major == 1:
        return -1 - n, i
    if major == 2:
        return bytes(data[i:i + n]), i + n
    if major == 3:
        return data[i:i + n].decode(), i + n
    if major == 4:
        out = []
        for _ in range(n):
            v, i = read_cbor(data, i)
            out.append(v)
        return out, i
    if major == 5:
        out = {}
        for _ in range(n):
            k, i = read_cbor(data, i)
            out[k], i = read_cbor(data, i)
        return out, i
    raise ValueError(major)


def read_snapshot(path):
    """The body of a snapshot file `{cid, body: bytes}`, checking the CID over the stored bytes."""
    with open(path, "rb") as f:
        outer, _ = read_cbor(f.read())
    body, _ = read_cbor(outer["body"])
    assert cid_of(body) == outer["cid"]
    return body


def write_snapshot(path, body):
    """A self-consistent snapshot of `body`: what a forger who recomputes the CID writes."""
    raw = cbor(body)
    with open(path, "wb") as f:
        f.write(cbor_head(5, 2) + cbor("cid") + cbor(cid_of(body)) + cbor("body") + cbor_head(2, len(raw)) + raw)


class Snapshots(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()

    def snapshots(self):
        return sorted(glob.glob(self.path + ".snapshot.*.cbor"))

    def snapshot(self):
        r = self.host.send(op="world-snapshot")
        self.assertEqual(r["status"], "snapshot", r)
        self.assertIn("height", r, r)
        return int(r["height"])

    def count(self, name):
        return field(self.state(name), "count")["value"]

    def reopen_report(self):
        self.reopen()
        opened = self.host.send(op="world-open", path=self.path)
        return opened["snapshot"]

    def test_smoke_bound_500_objects_reopen_from_a_snapshot_in_under_five_seconds(self):
        """The host's one wall-clock smoke bound, generous: measured 0.2 s on hbox."""
        for i in range(500):
            self.make(f"c{i}", PACKAGE, source_seed(i))
        self.assertEqual(self.turn("c7", "bump")["status"], "admitted")
        height = self.snapshot()
        self.assertEqual(self.turn("c9", "bump")["status"], "admitted")
        self.release()
        self.host = self.spawn()
        started = time.monotonic()
        opened = self.host.send(op="world-open", path=self.path)
        took = time.monotonic() - started
        self.assertEqual(opened["status"], "opened", opened)
        self.assertEqual(opened["snapshot"], {"resumed": height, "refused": []})
        self.assertEqual(opened["objects"], 500)
        self.assertLess(took, 5.0, f"reopen took {took:.2f} s")
        self.assertEqual((self.count("c7"), self.count("c9"), self.count("c499")), ("8", "10", "499"))
        # The resumed world runs turns, retries return their receipts, and history reads entries.
        again = self.turn("c7", "bump")
        self.assertEqual((again["status"], again["result"]), ("admitted", {"tag": "natural", "value": "9"}), again)
        retry = self.host.send(op="world-turn", principal="ember", object="c9", method="bump",
                               argument={"tag": "record", "fields": []}, identity="t2")
        self.assertEqual(retry["status"], "admitted", retry)
        history = self.host.send(op="world-history", principal="ember", object="c7")
        self.assertEqual(len(history["entries"]), 3, history)

    def test_a_snapshot_is_written_every_thousand_entries(self):
        self.make("c", PACKAGE, source_seed())  # the library entry is height 1, the create 2
        noted = []
        for i in range(1000):
            r = self.turn("c", "bump")
            self.assertEqual(r["status"], "admitted", r)
            if "snapshot" in r:
                noted.append((i, r["snapshot"]))
        self.assertEqual(noted, [(997, {"height": 1000})])
        [snap] = self.snapshots()
        self.assertTrue(snap.endswith(".snapshot.1000.cbor"), snap)
        self.assertEqual(self.reopen_report(), {"resumed": 1000, "refused": []})
        self.assertEqual(self.count("c"), "1000")

    def test_a_tampered_snapshot_is_refused_by_name_and_the_previous_one_used(self):
        self.make("a", PACKAGE, source_seed())
        first = self.snapshot()
        self.turn("a", "bump")
        second = self.snapshot()
        path = self.path + f".snapshot.{second}.cbor"
        with open(path, "rb") as f:
            data = bytearray(f.read())
        data[len(data) // 2] ^= 0x01
        with open(path, "wb") as f:
            f.write(data)
        report = self.reopen_report()
        self.assertEqual(report["resumed"], first, report)
        [(h, why)] = [(x["height"], x["reason"]) for x in report["refused"]]
        self.assertEqual(h, second)
        self.assertTrue("CID" in why or "CBOR" in why or "snapshot" in why or "UTF-8" in why, why)
        self.assertEqual(self.count("a"), "1")

    def test_a_snapshot_of_another_history_is_refused_by_its_head(self):
        self.make("a", PACKAGE, source_seed())
        height = self.snapshot()
        snap = self.path + f".snapshot.{height}.cbor"
        with open(snap, "rb") as f:
            data = f.read()
        # Another journal of the same length with another history.
        other = os.path.join(self.dir.name, "other.journal")
        self.host.send(op="world-open", path=other, library=self.library_path(), principal="ember")
        self.host.send(op="world-create", principal="ember", identity="mk-b", object="b", source=PACKAGE,
                       entry="initial", seed=source_seed(5))
        with open(other + f".snapshot.{height}.cbor", "wb") as f:
            f.write(data)
        self.release()
        h = self.spawn()
        opened = h.send(op="world-open", path=other)
        self.assertEqual(opened["snapshot"]["resumed"], 0, opened)
        self.assertIn("head", opened["snapshot"]["refused"][0]["reason"])
        self.assertEqual(h.send(op="world-view", principal="ember", object="b")["status"], "viewed")

    def library_path(self):
        from tests.test_reflection import LIBRARY
        return LIBRARY

    def test_a_consistent_forgery_is_refused_by_verify_as_disagreeing_with_replay(self):
        self.make("a", PACKAGE, source_seed())
        self.turn("a", "bump")
        height = self.snapshot()
        path = self.path + f".snapshot.{height}.cbor"
        body = read_snapshot(path)
        [obj] = body["objects"]
        self.assertEqual(obj["state"], {"tag": "record", "fields": [{"name": "count", "value": {"tag": "natural", "value": "1"}}]})
        obj["state"]["fields"][0]["value"]["value"] = "41"
        write_snapshot(path, body)
        self.release()
        self.host = self.spawn()
        checked = self.host.send(op="world-open", path=self.path, verify=True)
        self.assertEqual(checked["snapshot"]["refused"], [{"height": height, "reason": "it disagrees with replay at its height"}])
        self.assertEqual(self.count("a"), "1")

    def forge_count(self, value, recompute):
        self.make("a", PACKAGE, source_seed())
        self.turn("a", "bump")
        height = self.snapshot()
        path = self.path + f".snapshot.{height}.cbor"
        body = read_snapshot(path)
        [obj] = body["objects"]
        self.assertEqual(obj["stateCid"], cid_of(obj["state"]))
        obj["state"]["fields"][0]["value"]["value"] = value
        if recompute:
            obj["stateCid"] = cid_of(obj["state"])
        write_snapshot(path, body)
        return height

    def test_a_state_that_is_not_its_cids_is_refused_by_a_plain_open(self):
        height = self.forge_count("41", recompute=False)
        report = self.reopen_report()
        self.assertEqual(report["refused"], [{"height": height, "reason": "the state of a is not its CID's"}])
        self.assertEqual(self.count("a"), "1")

    def test_a_consistent_forgery_is_refused_by_a_plain_open_against_the_journals_write(self):
        # The forger recomputes the state's CID and the snapshot's; the bump's entry still commits to the real state.
        height = self.forge_count("41", recompute=True)
        report = self.reopen_report()
        self.assertEqual(report["refused"], [{"height": height, "reason": "the state of a is not the one the journal commits to at version 1"}])
        self.assertEqual(self.count("a"), "1")

    def test_a_snapshot_whose_version_is_not_the_journals_is_refused(self):
        self.make("a", PACKAGE, source_seed())
        self.turn("a", "bump")
        height = self.snapshot()
        path = self.path + f".snapshot.{height}.cbor"
        body = read_snapshot(path)
        body["objects"][0]["version"] = 7
        write_snapshot(path, body)
        report = self.reopen_report()
        self.assertEqual(report["resumed"], 0)
        self.assertIn("version", report["refused"][0]["reason"])
        self.assertEqual(self.count("a"), "1")

    def test_a_snapshot_keeps_suspended_activities_and_pending_deliveries(self):
        from tests.test_reflection import PROBE, probe_seed
        self.make("probe", PROBE, probe_seed())
        self.make("target", PROBE, probe_seed())
        waiting = self.host.send(op="world-turn", principal="ember", object="probe", method="ask",
                                 argument={"tag": "record", "fields": [
                                     {"name": "utterance", "value": {"tag": "label", "value": "bump it"}},
                                     {"name": "policy", "value": {"tag": "label", "value": "target"}}]},
                                 identity="wait")
        self.assertEqual(waiting["status"], "suspended", waiting)
        height = self.snapshot()
        self.assertEqual(self.reopen_report(), {"resumed": height, "refused": []})
        pending = self.host.send(op="world-interpretations")["pending"]
        self.assertEqual(len(pending), 1, pending)
        settled = self.host.send(op="world-interpretation", id=pending[0]["id"],
                                 reply={"status": "replied", "json": {"method": "bump2", "argument": {"n": 3}}})
        [resumed] = settled["resumed"]
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertEqual(self.count("probe"), "3")

    def test_a_snapshot_names_no_binary(self):
        # Binary identity is deploy's smoke test's; a snapshot binds the journal head and each state's CID.
        self.make("a", PACKAGE, source_seed())
        height = self.snapshot()
        body = read_snapshot(self.path + f".snapshot.{height}.cbor")
        self.assertNotIn("binary", body)
        self.assertEqual(self.reopen_report()["resumed"], height)


if __name__ == "__main__":
    unittest.main()
