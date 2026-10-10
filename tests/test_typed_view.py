"""A typed foreign view answers another package's state as the type the viewer names, checked by the
host.

Evidence for FOUNDATION §3 (layer: kernel).

Typed foreign views: `Plan.view::<S>({object})` is answered `viewed {version, state: S}`
for a first-order S the viewer's closure names, and the arm is typed by S. The compiler
lowers it to the Plan `viewAs {object, as}` naming the response arm `viewed:S`, which the
package's Plan and Response instances gain; the host answers that arm after checking the
viewed state against its declared type (the kernel refuses a response that does not
conform). A package without typed views compiles exactly as before.

    python3 -m unittest tests.test_typed_view -v
"""
import unittest

from tests.test_policy import context
from tests.test_turn import BINDING, Host, label, library_modules, nat, variant

POND = """edition ObjectiveBend 1
record State:
  count: Nat
  name: String
"""

VIEWER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./Pond.obend as Pond
record State:
  seen: Nat
record Edits:
  seen: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
def peek(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.view::<Pond.State>({object: {world: "", object: "pond"}})):
    case viewed(v): v.state.count
    case _: 0n
def mine(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  let viewed(v) = perform(Plan.view({object: Plans.self(context)}))
  v.state.seen
"""


def record(**fields):
    return {"tag": "record", "fields": [{"name": k, "value": v} for k, v in fields.items()]}


class TypedView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()
        modules = library_modules("Abi", "Plan") + [{"name": "Pond", "source": POND}, {"name": "Viewer", "source": VIEWER}]
        cls.modules = modules

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def compile(self, entry):
        reply = self.h.send({"op": "compile", "entry": entry, "modules": self.modules})
        self.assertEqual(reply["status"], "compiled", reply)
        return reply["artifact"]

    def start(self, art):
        return self.h.send(dict(BINDING, op="turn-start", artifact=art,
                                arguments=[record(seen=nat(2)), context("viewer")]))

    def test_a_typed_view_yields_view_as_and_its_arm_is_typed_by_the_viewed_state(self):
        art = self.compile("peek")
        y = self.start(art)
        self.assertEqual((y["status"], y["plan"]["label"]), ("yielded", "viewAs"), y)
        fields = {f["name"]: f["value"] for f in y["plan"]["payload"]["fields"]}
        arm = fields["as"]["value"]
        self.assertEqual(arm, "viewed:Pond.State")
        self.assertEqual(fields["object"], record(world=label(""), object=label("pond")))
        pond = record(count=nat(7), name=label("p"))
        done = self.h.send(dict(BINDING, op="turn-resume", artifact=art, checkpoint=y["checkpoint"],
                                response=variant(arm, record(version=nat(1), state=pond))))
        self.assertEqual((done["status"], done["value"]), ("finished", nat(7)), done)
        # A state that is not a Pond.State does not conform to the arm (the host's typeMismatch).
        wrong = self.h.send(dict(BINDING, op="turn-resume", artifact=art, checkpoint=y["checkpoint"],
                                 response=variant(arm, record(version=nat(1), state=record(seen=nat(1))))))
        self.assertEqual(wrong["status"], "error", wrong)
        self.assertIn("does not conform", wrong["message"])

    def test_the_untyped_view_of_the_own_state_still_works(self):
        art = self.compile("mine")
        y = self.start(art)
        self.assertEqual((y["status"], y["plan"]["label"]), ("yielded", "view"), y)
        done = self.h.send(dict(BINDING, op="turn-resume", artifact=art, checkpoint=y["checkpoint"],
                                response=variant("viewed", record(version=nat(3), state=record(seen=nat(5))))))
        self.assertEqual((done["status"], done["value"]), ("finished", nat(5)), done)


if __name__ == "__main__":
    unittest.main()
