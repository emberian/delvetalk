"""The compiler records an object's method table and the shape of its Bend law predicate in the
artifact, and refuses a law that is an activity or returns another sum.

Evidence for FOUNDATION §4, §5 (layer: kernel).

The compiler's method table and the shape of a package's Bend law predicate,
both recorded in the artifact.

    python3 -m unittest tests.test_methods -v
"""
import unittest

from tests.test_objects import compile_job, closure


LAW_HEAD = """edition ObjectiveBend 1
import ./World.obend as World
record State:
  count: Nat
record Request:
  kind: Nat
  subject: String
sum Verdict:
  admitted: {}
  refused: {clause: String}
def bump(state: State, input: {}, context: {}) -> Nat:
  state.count + 1n
"""


class LawShapeTests(unittest.TestCase):
    def compile(self, extra):
        return compile_job(closure("World") + [{"name": "Package", "source": LAW_HEAD + extra}], "bump")

    def test_a_pure_law_with_reads_is_recorded(self):
        reply = self.compile("""def law(old: State, new: State, request: Request) -> Verdict:
  if new.count < old.count then Verdict.refused({clause: "monotone"}) else Verdict.admitted({})
def lawReads() -> Nat:
  0n
""")
        self.assertEqual(reply["status"], "compiled", reply)
        self.assertEqual(reply["artifact"]["law"], {"present": True, "reads": True})

    def test_a_law_that_is_an_activity_is_refused_by_name(self):
        reply = self.compile("""def law(old: State, new: State, request: Request) -> Activity<Verdict>:
  Verdict.admitted({})
""")
        self.assertEqual(reply["status"], "error", reply)
        self.assertIn("law must not be an activity", reply["message"])

    def test_a_law_returning_another_sum_is_refused(self):
        reply = self.compile("""sum Answer:
  yes: {}
  no: {}
def law(old: State, new: State, request: Request) -> Answer:
  Answer.yes({})
""")
        self.assertEqual(reply["status"], "error", reply)
        self.assertIn("law must return Verdict", reply["message"])


if __name__ == "__main__":
    unittest.main()
