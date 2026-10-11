"""Scratch worlds and references across worlds (docs/FEDERATION.md §2, §3; HOST-HANDOFF 5.140).

Evidence for FOUNDATION §7 (layer: host). A principal opens a world of its own, empty or forked from the town at a
height with what it may view; it expires 360 town clock minutes after its last op, files and all, and says so; at
most two at once; an entry of it is kept in the town by `world-cite`; a turn in one world reads another's object
by `<world>:<object>` and journals the reading as a citation, not a root. Refuted by a scratch the town sees, a
fork carrying an object its principal may not view, a third scratch, a scratch that outlives its clock or leaves its
files, a citation that is not the scratch entry's bytes, or a foreign read that is not cited.
"""
import tempfile
import unittest
from pathlib import Path

from transport.host import HostClient
from transport.journal import entries as journal_entries
from tests.host import served as Served
from tests.test_reflection import WORLD_LIBRARY
from tests.wire import label, nat, record
from tests.bend import counter_modules, declared

DID = 'did:plc:' + 's' * 24
OTHER = 'did:plc:' + 't' * 24
OPENER = 'did:plc:' + 'o' * 24

READER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record Tally:
  count: Nat
record State:
  seen: Nat
def initial() -> State:
  {seen: 0n}
def peek(state: State, input: {world: String, object: String}, context: Abi.Context) -> Activity<Nat>:
  match world.view::<Tally>({object: {world: input.world, object: input.object}}):
    case viewed(v): v.state.count
    case denied(_): 0n
    case _: 999n
""", "peek")


class Scratch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / 'state'
        self.server = Served(str(self.state), opener=OPENER, library=WORLD_LIBRARY)
        self.addCleanup(self.server.stop)
        self.town = HostClient(self.server.sock)
        self.addCleanup(self.town.close)

    def at(self, name):
        client = HostClient(self.server.sock, world=f'scratch/{name}')
        self.addCleanup(client.close)
        return client

    def make(self, client, who, name, **extra):
        r = client.send({'op': 'world-create', 'principal': who, 'identity': 'mk-' + name, 'object': name,
                         'modules': counter_modules(), 'entry': 'initial', 'seed': record(count=nat(0)), **extra})
        self.assertEqual(r['status'], 'created', r)
        return r

    def bump(self, client, who, name, intent):
        return client.send({'op': 'world-turn', 'principal': who, 'object': name, 'method': 'bump', 'argument': record(),
                            'identity': intent})

    def test_a_scratch_is_its_principals_own_world_and_the_town_does_not_see_it(self):
        opened = self.town.send({'op': 'world-scratch', 'principal': DID, 'name': 'try'})
        self.assertEqual((opened['status'], opened['world']), ('scratch', 'scratch/try'), opened)
        mine = self.at('try')
        self.make(mine, DID, 'tally')
        self.assertEqual(self.bump(mine, DID, 'tally', 'b1')['status'], 'admitted')
        self.assertEqual(self.town.send({'op': 'world-view', 'principal': DID, 'object': 'tally'})['status'], 'unknown')
        # Another principal's `scratch/try` is its own, and none is open.
        self.assertIn('no scratch/try', self.at('try').send({'op': 'world-status', 'principal': OTHER})['message'])
        status = self.town.send({'op': 'serve-status'})
        self.assertEqual([(s['principal'], s['world']) for s in status['scratches']], [(DID, 'scratch/try')], status)
        self.assertEqual(self.town.send({'op': 'world-status'})['scratches'], {'open': 1, 'expiring': 0})
        self.assertIn('exists', self.town.send({'op': 'world-scratch', 'principal': DID, 'name': 'try'})['message'])
        self.assertEqual(self.town.send({'op': 'world-scratch', 'principal': DID, 'name': 'two'})['status'], 'scratch')
        third = self.town.send({'op': 'world-scratch', 'principal': DID, 'name': 'three'})
        self.assertEqual((third['status'], third['class'], third['oldest']['world']), ('refused', 'capacity', 'scratch/try'), third)
        # The hand expires a scratch now (the root act; the hand's log is its record), and a third may open.
        root = HostClient(self.server.root)
        self.addCleanup(root.close)
        gone = root.send({'op': 'world-root', 'principal': OPENER, 'reason': 'junk',
                          'act': {'kind': 'expire', 'principal': DID, 'scratch': 'try'}})
        self.assertEqual((gone['status'], gone['scratch']['world']), ('expired', 'scratch/try'), gone)
        self.assertIn('scratch/try expired', mine.send({'op': 'world-status', 'principal': DID})['message'])
        self.assertEqual(self.town.send({'op': 'world-scratch', 'principal': DID, 'name': 'three'})['status'], 'scratch')
        self.assertEqual(self.town.send({'op': 'world-root', 'principal': OPENER, 'reason': 'x',
                                         'act': {'kind': 'expire', 'principal': DID, 'scratch': 'two'}})['status'], 'error')

    def test_a_scratch_from_the_town_carries_only_what_its_principal_may_view(self):
        root = HostClient(self.server.root)
        self.addCleanup(root.close)
        self.make(self.town, DID, 'open')
        self.make(root, OPENER, 'closed', read={'principals': [OPENER]})
        height = self.town.send({'op': 'world-status'})['height']
        forked = self.town.send({'op': 'world-scratch', 'principal': DID, 'name': 'then', 'from': {'world': 'town', 'height': height}})
        self.assertEqual(forked['status'], 'scratch', forked)
        then = self.at('then')
        self.assertEqual(then.send({'op': 'world-view', 'principal': DID, 'object': 'open'})['status'], 'viewed')
        self.assertEqual(then.send({'op': 'world-view', 'principal': DID, 'object': 'closed'})['status'], 'unknown')

    def test_a_scratch_expires_by_the_town_clock_and_a_cited_entry_stays(self):
        self.town.send({'op': 'world-scratch', 'principal': DID, 'name': 'brief'})
        brief = self.at('brief')
        self.make(brief, DID, 'tally')
        bumped = self.bump(brief, DID, 'tally', 'b1')
        cited = self.town.send({'op': 'world-cite', 'principal': DID, 'scratch': 'brief', 'receipt': bumped['receipt']['hash']})
        self.assertEqual(cited['status'], 'cited', cited)
        self.assertEqual(self.town.send({'op': 'world-advance', 'principal': 'transport', 'height': 359})['status'], 'advanced')
        self.assertEqual(brief.send({'op': 'world-status', 'principal': DID})['status'], 'world')     # its last op now: 359
        self.town.send({'op': 'world-advance', 'principal': 'transport', 'height': 718})
        self.assertEqual(brief.send({'op': 'world-status', 'principal': DID})['status'], 'world')     # 359 + 360 is 719
        self.town.send({'op': 'world-advance', 'principal': 'transport', 'height': 1078})
        gone = brief.send({'op': 'world-status', 'principal': DID})
        self.assertIn('scratch/brief expired at clock 1078', gone['message'])
        self.assertEqual(list((self.state / 'scratch' / DID).iterdir()), [])
        # The town keeps what was cited: the scratch entry, whole, under its own hash.
        [kept] = [e for e in journal_entries(self.state / 'town.journal') if e['outcome']['tag'] == 'cited']
        self.assertEqual((kept['outcome']['world'], kept['outcome']['entry']['hash']), ('scratch/brief', bumped['receipt']['hash']))
        self.assertEqual(kept['outcome']['entry']['outcome']['tag'], 'admitted')
        # A citation of what the scratch never held is refused.
        self.town.send({'op': 'world-scratch', 'principal': DID, 'name': 'again'})
        self.assertIn('no entry', self.town.send({'op': 'world-cite', 'principal': DID, 'scratch': 'again', 'receipt': 'bafy'})['message'])

    def test_a_turn_reads_another_worlds_object_and_cites_it(self):
        self.town.send({'op': 'world-scratch', 'principal': DID, 'name': 'lab'})
        lab = self.at('lab')
        self.make(lab, DID, 'tally')
        for i in range(3):
            self.bump(lab, DID, 'tally', f'b{i}')
        made = self.town.send({'op': 'world-create', 'principal': DID, 'identity': 'mk-reader', 'object': 'reader',
                               'source': READER, 'entry': 'initial', 'seed': record()})
        self.assertEqual(made['status'], 'created', made)
        peek = lambda who, world, obj, intent: self.town.send({'op': 'world-turn', 'principal': who, 'object': 'reader', 'method': 'peek',
                                                               'argument': record(world=label(world), object=label(obj)), 'identity': intent})
        read = peek(DID, 'scratch/lab', 'tally', 'p1')
        self.assertEqual((read['status'], read['result']), ('admitted', nat(3)), read)
        [cite] = read['receipt']['cites']
        self.assertEqual((cite['world'], cite['object'], cite['version']), ('scratch/lab', 'tally', 3), cite)
        self.assertNotIn('tally', [r['object'] for r in read['receipt']['roots']])
        # Another principal's `scratch/lab` is its own, which it has not opened: not served here.
        self.assertEqual(peek(OTHER, 'scratch/lab', 'tally', 'p2')['result'], nat(999))
        self.assertEqual(peek(DID, 'ring', 'tally', 'p3')['result'], nat(999))
        # Read by the ops, as of the other world's height.
        viewed = self.town.send({'op': 'world-view', 'principal': DID, 'object': 'scratch/lab:tally'})
        self.assertEqual((viewed['status'], viewed['asOf']['world'], viewed['asOf']['version']), ('viewed', 'scratch/lab', 3), viewed)


if __name__ == '__main__':
    unittest.main()
