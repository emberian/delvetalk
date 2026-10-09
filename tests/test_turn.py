"""Turn-by-turn activity execution through delvetalk-obend (turn-start / turn-resume).

Each test names what would refute it. One host process per test unless the test
is about process boundaries.
"""
import copy
import json
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BINARY = os.path.join(ROOT, ".lake", "build", "bin", "delvetalk-obend")

PLANS = """edition ObjectiveBend 1
record Edit:
  field: Nat
  before: Nat
  after: Nat
sum Plan:
  write: Edit
sum Reply:
  written: {}
  refused: {}
def bump(count: Nat) -> Activity<Plan, Reply, Nat>:
  match perform(Plan.write({field: 0n, before: count, after: count + 1n})):
    case written(_): count + 1n
    case refused(_): count
def twice(count: Nat) -> Activity<Plan, Reply, Nat>:
  match perform(Plan.write({field: 0n, before: count, after: count + 1n})):
    case written(_):
      match perform(Plan.write({field: 1n, before: count + 1n, after: count + 2n})):
        case written(_): count + 2n
        case refused(_): count + 1n
    case refused(_): count
def pure(n: Nat) -> Nat:
  n + 1n
"""


def wide_source():
    fields = "\n".join(f"  f{i}: Nat" for i in range(63))
    values = ", ".join(f"f{i}: {i}n" for i in range(63))
    return f"""edition ObjectiveBend 1
record Wide:
  text: String
{fields}
sum Plan:
  big: Wide
sum Reply:
  ok: {{}}
def wide(text: String) -> Activity<Plan, Reply, Nat>:
  match perform(Plan.big({{text: text, {values}}})):
    case ok(_): 1n
"""


def nat(n):
    return {"tag": "natural", "value": str(n)}


def label(s):
    return {"tag": "label", "value": s}


def variant(name, payload=None):
    return {"tag": "variant", "label": name,
            "payload": payload or {"tag": "record", "fields": []}}


def plan_field(plan, name):
    for f in plan["fields"]:
        if f["name"] == name:
            return f["value"]
    raise KeyError(name)


class Host:
    def __init__(self):
        self.proc = subprocess.Popen([BINARY], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, bufsize=1)

    def send(self, request):
        self.proc.stdin.write(json.dumps(request) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        assert line, "host closed its output (crash)"
        return json.loads(line)

    def compile(self, source, entry):
        reply = self.send({"op": "compile", "entry": entry,
                           "modules": [{"name": "Package", "source": source}]})
        assert reply["status"] == "compiled", reply
        return reply["artifact"]

    def start(self, artifact, arguments, **limits):
        request = {"op": "turn-start", "artifact": artifact, "arguments": arguments}
        if limits:
            request["limits"] = limits
        return self.send(request)

    def resume(self, artifact, checkpoint, response, **limits):
        request = {"op": "turn-resume", "artifact": artifact, "checkpoint": checkpoint,
                   "response": response}
        if limits:
            request["limits"] = limits
        return self.send(request)

    def close(self):
        self.proc.stdin.close()
        self.proc.stdout.close()
        self.proc.wait(timeout=30)


class TurnCase(unittest.TestCase):
    def host(self):
        h = Host()
        self.addCleanup(h.close)
        return h


class TurnTests(TurnCase):
    def test_bump_yields_write_then_written_finishes_after_value(self):
        h = self.host()
        art = h.compile(PLANS, "bump")
        y = h.start(art, [nat(3)])
        self.assertEqual(y["status"], "yielded", y)
        self.assertEqual(plan_field(y["plan"]["payload"], "before"), nat(3))
        self.assertEqual(plan_field(y["plan"]["payload"], "after"), nat(4))
        self.assertEqual(y["plan"]["label"], "write")
        done = h.resume(art, y["checkpoint"], variant("written"))
        self.assertEqual((done["status"], done["value"]), ("finished", nat(4)), done)

    def test_bump_refused_response_finishes_with_unchanged_value(self):
        h = self.host()
        art = h.compile(PLANS, "bump")
        y = h.start(art, [nat(3)])
        done = h.resume(art, y["checkpoint"], variant("refused"))
        self.assertEqual((done["status"], done["value"]), ("finished", nat(3)), done)

    def test_activity_that_performs_twice_yields_twice_then_finishes(self):
        h = self.host()
        art = h.compile(PLANS, "twice")
        first = h.start(art, [nat(10)])
        self.assertEqual(first["status"], "yielded", first)
        self.assertEqual(plan_field(first["plan"]["payload"], "after"), nat(11))
        second = h.resume(art, first["checkpoint"], variant("written"))
        self.assertEqual(second["status"], "yielded", second)
        self.assertEqual(plan_field(second["plan"]["payload"], "field"), nat(1))
        self.assertEqual(plan_field(second["plan"]["payload"], "after"), nat(12))
        done = h.resume(art, second["checkpoint"], variant("written"))
        self.assertEqual((done["status"], done["value"]), ("finished", nat(12)), done)

    def test_nonconforming_response_is_refused_and_checkpoint_stays_usable(self):
        h = self.host()
        art = h.compile(PLANS, "bump")
        y = h.start(art, [nat(3)])
        for bad in (variant("nonsense"), nat(1), variant("written", nat(1)),
                    {"tag": "record", "fields": []}):
            r = h.resume(art, y["checkpoint"], bad)
            self.assertEqual(r["status"], "error", r)
            self.assertIn("does not conform", r["message"])
        done = h.resume(art, y["checkpoint"], variant("written"))
        self.assertEqual((done["status"], done["value"]), ("finished", nat(4)), done)

    def test_tampered_checkpoint_is_refused_by_name(self):
        h = self.host()
        art = h.compile(PLANS, "bump")
        y = h.start(art, [nat(3)])
        cp = y["checkpoint"]
        self.assertGreater(len(cp), 10)
        tampered = []
        edition = copy.deepcopy(cp); edition[0] = {"s": "other.edition"}; tampered.append(edition)
        tampered.append(cp[:-1])
        tampered.append(cp + [{"n": "0"}])
        swapped = copy.deepcopy(cp); swapped[2] = {"s": "x"}; tampered.append(swapped)
        tampered.append([{"n": "-1"}])
        tampered.append([])
        for t in tampered:
            r = h.resume(art, t, variant("written"))
            self.assertEqual(r["status"], "error", r)
            self.assertEqual(r["message"], "checkpoint does not decode", r)

    def test_tick_exhaustion_on_resume_is_a_named_error_not_a_crash(self):
        h = self.host()
        art = h.compile(PLANS, "bump")
        y = h.start(art, [nat(3)])
        r = h.resume(art, y["checkpoint"], variant("written"), ticks=1)
        self.assertEqual(r["status"], "error", r)
        self.assertIn("tick budget exhausted", r["message"])
        s = h.start(art, [nat(3)], ticks=1)
        self.assertEqual(s["status"], "error", s)
        self.assertIn("tick budget exhausted", s["message"])
        # the host survived both
        done = h.resume(art, y["checkpoint"], variant("written"))
        self.assertEqual(done["status"], "finished", done)

    def test_checkpoint_from_one_process_resumes_in_a_fresh_process(self):
        first = Host()
        art = first.compile(PLANS, "twice")
        y = first.start(art, [nat(5)])
        first.close()
        self.assertEqual(y["status"], "yielded", y)
        second = self.host()
        art2 = second.compile(PLANS, "twice")
        self.assertEqual(art, art2)
        mid = second.resume(art2, y["checkpoint"], variant("written"))
        self.assertEqual(mid["status"], "yielded", mid)
        third = Host()
        art3 = third.compile(PLANS, "twice")
        done = third.resume(art3, mid["checkpoint"], variant("refused"))
        third.close()
        self.assertEqual((done["status"], done["value"]), ("finished", nat(6)), done)

    def test_pure_entry_given_to_turn_start_is_refused_by_name(self):
        h = self.host()
        art = h.compile(PLANS, "pure")
        r = h.start(art, [nat(1)])
        self.assertEqual(r["status"], "error", r)
        self.assertIn("entry is not an activity", r["message"])
        r = h.resume(art, [], variant("written"))
        self.assertEqual(r["status"], "error", r)
        self.assertIn("entry is not an activity", r["message"])

    def test_resume_of_a_checkpoint_whose_control_is_not_yielded_is_refused(self):
        h = self.host()
        art = h.compile(PLANS, "bump")
        y = h.start(art, [nat(3)])
        cp = copy.deepcopy(y["checkpoint"])
        # bump yields under one `case` frame: the control is [6 (yielded), plan address]
        # followed by the stack length 1 and the case frame tag 10.
        spots = [i for i in range(len(cp) - 3)
                 if [t.get("n") for t in cp[i:i + 4:1]][0] == "6"
                 and cp[i + 2].get("n") == "1" and cp[i + 3].get("n") == "10"]
        self.assertEqual(len(spots), 1, spots)
        cp[spots[0]] = {"n": "1"}  # the same address as an `enter` control instead
        r = h.resume(art, cp, variant("written"))
        self.assertEqual(r["status"], "error", r)
        self.assertIn("not a yielded state", r["message"])

    def test_maximum_plan_record_and_long_label_round_trip(self):
        h = self.host()
        art = h.compile(wide_source(), "wide")
        text = "é" * 2048  # 4096 UTF-8 bytes
        self.assertEqual(len(text.encode()), 4096)
        y = h.start(art, [label(text)])
        self.assertEqual(y["status"], "yielded", y)
        self.assertEqual(y["plan"]["label"], "big")
        fields = y["plan"]["payload"]["fields"]
        self.assertEqual(len(fields), 64)
        self.assertEqual(plan_field(y["plan"]["payload"], "text"), label(text))
        self.assertEqual(plan_field(y["plan"]["payload"], "f62"), nat(62))
        done = h.resume(art, y["checkpoint"], variant("ok"))
        self.assertEqual((done["status"], done["value"]), ("finished", nat(1)), done)


if __name__ == "__main__":
    unittest.main()
