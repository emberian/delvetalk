"""Turn-by-turn activity execution through delvetalk-obend (turn-start / turn-resume).

Each test names what would refute it. One host process per test unless the test
is about process boundaries.
"""
import copy
import hashlib
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


def redigest(checkpoint):
    """Recompute a checkpoint's digest after editing its tokens (SHA-256 of the
    compact token JSON), so a test can get past the digest to the decoder."""
    text = json.dumps(checkpoint["tokens"], separators=(",", ":"), ensure_ascii=False)
    checkpoint["digest"] = hashlib.sha256(text.encode()).hexdigest()
    return checkpoint


def with_tokens(checkpoint, tokens, fix_digest):
    c = copy.deepcopy(checkpoint)
    c["tokens"] = tokens
    return redigest(c) if fix_digest else c


LISTS = """edition ObjectiveBend 1
sum List<T>:
  nil: {}
  cons: {head: T, tail: List<T>}
sum Plan:
  put: List<Nat>
sum Reply:
  names: List<String>
  none: {}
def range(n: Nat) -> List<Nat>:
  match n:
    case 0n: List::<Nat>.nil({})
    case 1n+p: List::<Nat>.cons({head: n, tail: range(p)})
def count(items: List<String>) -> Nat:
  match items:
    case nil(_): 0n
    case cons(c): 1n + count(c.tail)
def collect(n: Nat) -> Activity<Plan, Reply, Nat>:
  match perform(Plan.put(range(n))):
    case names(items): count(items)
    case none(_): 0n
"""

DOCUMENTS = """edition ObjectiveBend 1
import ./Document.obend as Doc
sum Plan:
  offer: Doc.Document
sum Reply:
  back: Doc.Document
def show(label: String) -> Activity<Plan, Reply, Nat>:
  match perform(Plan.offer(Doc.concat(Doc.text(label), Doc.quote("a", Doc.text("b"))))):
    case back(d): Doc.size(d)
"""

WORLD_LIB = os.path.join(ROOT, "world", "lib")


def library_modules(*names):
    """Library modules (imports first) read from world/lib, as supplied modules."""
    found = {}
    for directory, _, files in os.walk(WORLD_LIB):
        for f in files:
            if f.endswith(".obend"):
                found[f[:-6]] = os.path.join(directory, f)
    out, seen = [], set()

    def visit(name):
        if name in seen:
            return
        seen.add(name)
        with open(found[name]) as handle:
            source = handle.read()
        for line in source.splitlines():
            if line.startswith("import ./"):
                visit(line.split("/")[1].split(".obend")[0])
        out.append({"name": name, "source": source})
    for n in names:
        visit(n)
    return out


def nil():
    return variant("nil")


def cons(head, tail):
    return variant("cons", {"tag": "record", "fields": [
        {"name": "head", "value": head}, {"name": "tail", "value": tail}]})


def from_list(items):
    out = nil()
    for item in reversed(items):
        out = cons(item, out)
    return out


def to_list(data):
    out = []
    while data["label"] == "cons":
        fields = {f["name"]: f["value"] for f in data["payload"]["fields"]}
        out.append(fields["head"])
        data = fields["tail"]
    return out


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

    def compile(self, source, entry, library=()):
        reply = self.send({"op": "compile", "entry": entry,
                           "modules": library_modules(*library) + [{"name": "Package", "source": source}]})
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


WALK = """edition ObjectiveBend 1
def walk(text: String, n: Nat) -> Nat:
  match n:
    case 0n: 0n
    case 1n+p: textLength(textTake(text, 1n)) + walk(textDrop(text, 1n), p)
"""


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
        toks = cp["tokens"]
        self.assertGreater(len(toks), 10)
        edition = copy.deepcopy(toks); edition[0] = {"s": "other.edition"}
        swapped = copy.deepcopy(toks); swapped[2] = {"s": "x"}
        variants = [edition, toks[:-1], toks + [{"n": "0"}], swapped, []]
        # stale digest: refused by digest, before any decoding
        for t in variants:
            r = h.resume(art, with_tokens(cp, t, False), variant("written"))
            self.assertEqual((r["status"], r["message"]), ("error", "checkpoint digest mismatch"), r)
        # a forged digest gets past the digest and is then refused by the decoder
        for t in variants:
            r = h.resume(art, with_tokens(cp, t, True), variant("written"))
            self.assertEqual((r["status"], r["message"]), ("error", "checkpoint does not decode"), r)
        # a token that is not a canonical natural never reaches the digest
        r = h.resume(art, with_tokens(cp, [{"n": "-1"}], False), variant("written"))
        self.assertEqual(r["message"], "checkpoint does not decode", r)
        # missing or malformed envelope
        for bad in ([], {"tokens": toks}, {**cp, "digest": 7}):
            self.assertEqual(h.resume(art, bad, variant("written"))["status"], "error")

    def test_token_edit_that_still_decodes_is_refused_by_the_digest(self):
        h = self.host()
        art = h.compile(PLANS, "bump")
        y = h.start(art, [nat(3)])
        cp = y["checkpoint"]
        toks = cp["tokens"]
        edited = None
        for i in range(len(toks) - 1):
            if toks[i] == {"n": "10"} and toks[i + 1] == {"n": "1"}:  # a literal `1n` term
                t = copy.deepcopy(toks); t[i + 1] = {"n": "7"}
                probe = h.resume(art, with_tokens(cp, t, True), variant("written"))
                if probe["status"] == "finished" and probe["value"] != nat(4):
                    edited, forged = t, probe
                    break
        self.assertIsNotNone(edited, "no decodable single-token edit found")
        self.assertNotEqual(forged["value"], nat(4))  # the edit changes behaviour...
        r = h.resume(art, with_tokens(cp, edited, False), variant("written"))
        self.assertEqual((r["status"], r["message"]), ("error", "checkpoint digest mismatch"), r)
        # ... and the untouched checkpoint still works
        done = h.resume(art, cp, variant("written"))
        self.assertEqual(done["value"], nat(4), done)

    def test_checkpoint_from_package_a_is_refused_by_package_b(self):
        h = self.host()
        a = h.compile(PLANS, "bump")
        b = h.compile(PLANS, "twice")  # same sources, different entry: different packet
        self.assertNotEqual(a["packetSha256"], b["packetSha256"])
        y = h.start(a, [nat(3)])
        r = h.resume(b, y["checkpoint"], variant("written"))
        self.assertEqual((r["status"], r["message"]), ("error", "checkpoint belongs to another package"), r)
        self.assertEqual(h.resume(a, y["checkpoint"], variant("written"))["status"], "finished")

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
        other = h.compile(PLANS, "bump")
        cp = h.start(other, [nat(1)])["checkpoint"]
        r = h.resume(art, cp, variant("written"))
        self.assertEqual(r["status"], "error", r)
        self.assertIn("entry is not an activity", r["message"])

    def test_resume_of_a_checkpoint_whose_control_is_not_yielded_is_refused(self):
        h = self.host()
        art = h.compile(PLANS, "bump")
        y = h.start(art, [nat(3)])
        cp = copy.deepcopy(y["checkpoint"])
        toks = cp["tokens"]
        # bump yields under one `case` frame: the control is [6 (yielded), plan address]
        # followed by the stack length 1 and the case frame tag 10.
        spots = [i for i in range(len(toks) - 3)
                 if toks[i].get("n") == "6"
                 and toks[i + 2].get("n") == "1" and toks[i + 3].get("n") == "10"]
        self.assertEqual(len(spots), 1, spots)
        toks[spots[0]] = {"n": "1"}
        redigest(cp)  # the same address as an `enter` control instead
        r = h.resume(art, cp, variant("written"))
        self.assertEqual(r["status"], "error", r)
        self.assertIn("not a yielded state", r["message"])

    def test_recursive_list_in_a_plan_with_100_elements_yields_and_resumes(self):
        h = self.host()
        art = h.compile(LISTS, "collect")
        y = h.start(art, [nat(100)])
        self.assertEqual(y["status"], "yielded", y)
        self.assertEqual(y["plan"]["label"], "put")
        self.assertEqual([x["value"] for x in to_list(y["plan"]["payload"])],
                         [str(n) for n in range(100, 0, -1)])
        done = h.resume(art, y["checkpoint"], variant("none"))
        self.assertEqual((done["status"], done["value"]), ("finished", nat(0)), done)

    def test_recursive_list_response_conforms_and_a_malformed_cons_is_refused(self):
        h = self.host()
        art = h.compile(LISTS, "collect")
        y = h.start(art, [nat(2)])
        good = variant("names", from_list([label("a"), label("b"), label("c")]))
        done = h.resume(art, y["checkpoint"], good)
        self.assertEqual((done["status"], done["value"]), ("finished", nat(3)), done)
        missing_tail = variant("names", variant("cons", {"tag": "record", "fields": [
            {"name": "head", "value": label("a")}]}))
        wrong_head = variant("names", from_list([label("a"), nat(7)]))
        extra_field = variant("names", variant("cons", {"tag": "record", "fields": [
            {"name": "head", "value": label("a")}, {"name": "tail", "value": nil()},
            {"name": "more", "value": nat(1)}]}))
        wrong_tail = variant("names", variant("cons", {"tag": "record", "fields": [
            {"name": "head", "value": label("a")}, {"name": "tail", "value": nat(0)}]}))
        for bad in (missing_tail, wrong_head, extra_field, wrong_tail):
            r = h.resume(art, y["checkpoint"], bad)
            self.assertEqual(r["status"], "error", r)
            self.assertIn("does not conform", r["message"])
        # the checkpoint is still usable
        self.assertEqual(h.resume(art, y["checkpoint"], good)["status"], "finished")

    def test_document_in_a_plan_round_trips_through_the_response(self):
        h = self.host()
        art = h.compile(DOCUMENTS, "show", library=("Document",))
        y = h.start(art, [label("hello")])
        self.assertEqual(y["status"], "yielded", y)
        self.assertEqual(y["plan"]["label"], "offer")
        document = y["plan"]["payload"]
        self.assertEqual(document["label"], "sequence")
        done = h.resume(art, y["checkpoint"], variant("back", document))
        # size = len("hello") + len("a") + len("b")
        self.assertEqual((done["status"], done["value"]), ("finished", nat(7)), done)
        broken = copy.deepcopy(document)
        broken["label"] = "no-such-document-form"
        r = h.resume(art, y["checkpoint"], variant("back", broken))
        self.assertEqual(r["status"], "error", r)

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


class TextTariffTests(TurnCase):
    def walk(self, h, art, steps, ticks=None):
        request = {"op": "run", "artifact": art, "arguments": [label("a" * 4096), nat(steps)]}
        if ticks:
            request["limits"] = {"ticks": str(ticks)}
        return h.send(request)

    def test_character_walk_cost_is_linear_not_quadratic_in_the_input(self):
        h = self.host()
        art = h.compile(WALK, "walk")
        # 1024 one-character steps over a 4096-byte string fit the DEFAULT budget
        small = self.walk(h, art, 1024)
        self.assertEqual((small["status"], small["value"]), ("finished", nat(1024)), small)
        self.assertLess(small["ticksUsed"], 100000)
        # the whole 4096-byte string, one character at a time, under 300,000 ticks
        whole = self.walk(h, art, 4096, 300000)
        self.assertEqual((whole["status"], whole["value"]), ("finished", nat(4096)), whole)
        # 4x the steps costs about 4x the ticks (a whole-input charge would be 4x per step too)
        self.assertLess(whole["ticksUsed"], 4.5 * small["ticksUsed"])


if __name__ == "__main__":
    unittest.main()
