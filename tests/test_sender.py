"""`context.sender`: the object whose send a turn delivers, the same in every frame of that turn and in
its law's context, "" for a turn a principal began; `caller` stays the frame's calling object.

Evidence for HOST-HANDOFF §5.1 (layer: host). Refuted by a delivered turn whose frames or law see
another sender, a direct turn that sees one, or a replay that judges the law otherwise.

    python3 -W error -m unittest tests.test_sender -v
"""
import unittest

from tests.test_reflection import Reflection
from tests.wire import label, record
from tests.bend import declared

# The weather pours: a send of `rain` to the bell, and a call of the bell's `rain` (its own frame).
WEATHER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def bell() -> Plans.Reference:
  {world: "", object: "bell"}
def pour(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.send({object: bell(), method: "rain", argument: {}}):
    case delivery(_): 1n
    case _: 0n
def drip(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.call::<Nat>({object: bell(), method: "rain", argument: {}}):
    case returned(r): r.result
    case _: 0n
""")

# The bell writes who sent the turn and who called the frame, then calls the ledger, which writes
# the same of its own frame. Its Bend law refuses a rain sent by the hail.
BELL = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  seen: String
def initial() -> State:
  {seen: ""}
def rain(state: State, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {seen: Plans.Edit.set({value: "sender={context.sender} caller={context.caller}"})}))
  match world.call::<Nat>({object: {world: "", object: "ledger"}, method: "note", argument: {}}):
    case returned(r): r.result
    case _: 0n
def law(old: State, new: State, request: Abi.Request) -> Abi.Verdict:
  if request.context.sender == "hail" then Abi.Verdict.refused({clause: "hail", reading: "no rain from the hail"}) else Abi.Verdict.admitted({})
""")

LEDGER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  seen: String
def initial() -> State:
  {seen: ""}
def note(state: State, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {seen: Plans.Edit.set({value: "sender={context.sender} caller={context.caller}"})}))
  7n
""")


class Sender(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        for name, source in (("weather", WEATHER), ("hail", WEATHER), ("bell", BELL), ("ledger", LEDGER)):
            self.make(name, source, record())

    def test_a_delivered_turn_names_its_sender_in_every_frame_and_a_direct_one_names_none(self):
        poured = self.turn("weather", "pour")
        self.assertEqual((poured["status"], [d["status"] for d in poured["delivered"]]), ("admitted", ["admitted"]), poured)
        self.assertEqual(self.seen("bell"), "sender=weather caller=weather")
        self.assertEqual(self.seen("ledger"), "sender=weather caller=bell")
        # A call from a turn a principal began: a caller, no sender.
        self.assertEqual(self.turn("weather", "drip")["status"], "admitted")
        self.assertEqual((self.seen("bell"), self.seen("ledger")), ("sender= caller=weather", "sender= caller=bell"))
        self.assertEqual(self.turn("bell", "rain")["status"], "admitted")
        self.assertEqual(self.seen("bell"), "sender= caller=")

    def test_the_law_reads_the_sender_and_replay_judges_it_alike(self):
        hailed = self.turn("hail", "pour")
        [rain] = hailed["delivered"]
        out = rain["receipt"]["outcome"]
        self.assertEqual((hailed["status"], rain["status"], out["clause"], out["reading"]), ("admitted", "refused", "hail", "no rain from the hail"), hailed)
        # A hail called (no sender) passes the same law.
        self.assertEqual(self.turn("hail", "drip")["status"], "admitted")
        self.assertEqual(self.turn("weather", "pour")["status"], "admitted")
        self.assertEqual(self.seen("bell"), "sender=weather caller=weather")
        verified = self.host.send(op="world-open", path=self.path, verify=True)
        self.assertEqual((verified["status"], verified["snapshot"]["refused"]), ("opened", []), verified)


if __name__ == "__main__":
    unittest.main()
