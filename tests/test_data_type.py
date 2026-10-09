"""The universal first-order type `Data` (`Data.of::<T>(value)`, no elimination).

Each test names what would refute it.
"""
import unittest

from tests.test_turn import Host, nat, label, variant

CALLER = """edition ObjectiveBend 1
record Call:
  object: String
  method: String
  argument: Data
sum Plan:
  call: Call
sum Reply:
  returned: {result: Data}
  refused: {}
record Pair:
  a: Nat
  b: String
sum Shade:
  dark: {}
  light: {level: Nat}
def fan(count: Nat) -> Activity<Plan, Reply, Data>:
  match perform(Plan.call({object: "counter", method: "add", argument: Data.of::<Nat>(count)})):
    case returned(first):
      match perform(Plan.call({object: "pairs", method: "put", argument: Data.of::<Pair>({a: count, b: "hi"})})):
        case returned(second): second.result
        case refused(_): first.result
    case refused(_): Data.of::<Shade>(Shade.dark({}))
def keep(value: Data, n: Nat) -> Activity<Plan, Reply, Data>:
  match perform(Plan.call({object: "box", method: "put", argument: value})):
    case returned(r): r.result
    case refused(_): value
def pair(p: Pair) -> Activity<Plan, Reply, Nat>:
  match perform(Plan.call({object: "pairs", method: "put", argument: Data.of::<Pair>(p)})):
    case returned(_): p.a
    case refused(_): 0n
"""


def field(record, name):
    for f in record["fields"]:
        if f["name"] == name:
            return f["value"]
    raise KeyError(name)


def record(**fields):
    return {"tag": "record", "fields": [{"name": k, "value": v} for k, v in fields.items()]}


class DataTypeTests(unittest.TestCase):
    def host(self):
        h = Host()
        self.addCleanup(h.close)
        return h

    def test_one_activity_calls_two_objects_with_different_argument_shapes(self):
        # Refuted if a single Plan type cannot carry a Nat and a record payload in one activity.
        h = self.host()
        art = h.compile(CALLER, "fan")
        first = h.start(art, [nat(5)])
        self.assertEqual(first["status"], "yielded", first)
        self.assertEqual(field(first["plan"]["payload"], "argument"), nat(5))
        self.assertEqual(first["planType"]["row"]["member"]["tail"]["tail"]["member"], {"tag": "data"})
        second = h.resume(art, first["checkpoint"], variant("returned", record(result=nat(6))))
        self.assertEqual(second["status"], "yielded", second)
        self.assertEqual(field(second["plan"]["payload"], "argument"), record(a=nat(5), b=label("hi")))

    def test_data_field_round_trips_through_a_checkpoint(self):
        # Refuted if a Data value (here a variant inside a record) changes across yield/resume.
        h = self.host()
        art = h.compile(CALLER, "keep")
        value = record(shade=variant("light", record(level=nat(3))), tags=label("x"))
        started = h.start(art, [value, nat(0)])
        self.assertEqual(started["status"], "yielded", started)
        self.assertEqual(field(started["plan"]["payload"], "argument"), value)
        echoed = variant("on", record(deep=variant("light", record(level=nat(4)))))
        done = h.resume(art, started["checkpoint"], variant("returned", record(result=echoed)))
        self.assertEqual(done["status"], "finished", done)
        self.assertEqual(done["value"], echoed)
        self.assertEqual(done["type"], {"tag": "data"})

    def test_data_argument_with_a_repeated_field_is_refused(self):
        # Refuted if Data admits a record that is not well-formed data.
        h = self.host()
        art = h.compile(CALLER, "keep")
        bad = {"tag": "record", "fields": [{"name": "a", "value": nat(1)}, {"name": "a", "value": nat(2)}]}
        reply = h.start(art, [bad, nat(0)])
        self.assertEqual(reply["status"], "error", reply)
        self.assertIn("does not conform", reply["message"])

    def test_argument_shape_not_conforming_to_the_declared_type_is_refused(self):
        # Refuted if a Data payload of the wrong shape reaches a callee typed Pair.
        h = self.host()
        art = h.compile(CALLER, "pair")
        reply = h.start(art, [record(a=nat(1))])
        self.assertEqual(reply["status"], "error", reply)
        self.assertEqual(reply["message"], "turn refused: argument does not conform to its type")
        ok = h.start(art, [record(a=nat(1), b=label("x"))])
        self.assertEqual(ok["status"], "yielded", ok)

    def test_data_of_checks_its_declared_type_and_has_no_elimination(self):
        # Refuted if Data.of accepts a value of another type, or Bend can take Data apart.
        h = self.host()
        wrong = h.send({"op": "compile", "entry": "f", "modules": [{"name": "Package", "source":
            "edition ObjectiveBend 1\ndef f(n: Nat) -> Data:\n  Data.of::<String>(n)\n"}]})
        self.assertEqual(wrong["status"], "error", wrong)
        self.assertIn("Data.of::<String>", wrong["message"])
        eliminate = h.send({"op": "compile", "entry": "g", "modules": [{"name": "Package", "source":
            "edition ObjectiveBend 1\ndef g(d: Data) -> Nat:\n  d + 1n\n"}]})
        self.assertEqual(eliminate["status"], "error", eliminate)
        good = h.send({"op": "compile", "entry": "f", "modules": [{"name": "Package", "source":
            "edition ObjectiveBend 1\ndef f(n: Nat) -> Data:\n  Data.of::<Nat>(n)\n"}]})
        self.assertEqual(good["status"], "compiled", good)


if __name__ == "__main__":
    unittest.main()
