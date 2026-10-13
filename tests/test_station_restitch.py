"""A station stitched from 92584b09's scene, carried and refreshed from the shipped scene.

Refuted by an old passage/guard/rule surviving refresh, a reader or their variables changing,
owner clauses disappearing, repeated scene rules, a cached rollback, or a stranger replacing a wing.
"""
import copy
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from deploy import genesis
from tests.host import binary
from tests.test_objects import run_pure
from tests.town import Town
from tests.wire import cast_refusal, field, label, nat, record, rows
from transport import journal
from transport.carry import body_args
from transport.config import LIBRARY
from transport.host import HostProcess

OPENER = genesis.OPENER
READER, OTHER = 'did:plc:station-reader', 'did:plc:station-other'
OWNER_CLAUSE_HEAD = 'law owner_after "the owner keeps this clause": '
# The old scene has no reader-local effects. Its owner's fixture method writes a reader's memory
# through the host, under the ordinary room law, before the carry replaces this body.
MEMORY = '''
form remember:
  who: text 1..128
def remember(state: State, input: RememberInput, context: Abi.Context) -> Activity<Done>:
  if context.principal != state.owner then Super.roomRefused({clause: "notOwner", reading: "The owner sets the fixture memory."}, context) else remembered(input.who)
def remembered(who: String) -> Activity<Done>:
  let written(_) = write {mine: upsert {who: who, name: "cups", value: "2"}}
  Done.done({})
'''
SCENE_PROBE = '''edition ObjectiveBend 1
import ./Spween.obend as Spween
import ./Scenes.obend as Scenes
def rules(text: String) -> String:
  match Spween.wing(text):
    case parsed(p): Scenes.ruleText(p.seed.passages)
    case refused(r): "refused: {r.reason}"
'''


def state(host, obj='station'):
    return host.send(op='world-view', principal=OPENER, object=obj)['state']


def law(host):
    return host.send(op='world-object', principal=OPENER, object='station')['record']['law']


def scene_stamp(st):
    stamps = [m for m in rows(field(st, 'marks')) if field(m, 'name')['value'].startswith('station-scene-')]
    return field(max(stamps, key=lambda m: int(field(m, 'at')['value'])), 'name')['value'][14:78] if stamps else None


class StationRestitch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        fixtures = Path(__file__).resolve().parent / 'fixtures'
        cls.old_scene = (fixtures / 'station-92584b09.spween').read_text()
        cls.shipped_scene = genesis.station_scene()
        assert cls.old_scene != cls.shipped_scene
        # This body predates digest marks and has the carried room's mine/draw interfaces.
        legacy = (fixtures / 'station-ed7465f6.obend').read_text() + MEMORY
        cls.town = Town(os.path.join(cls.tmp.name, 'old'), cleanup=cls.addClassCleanup, furnished=False)
        body_of = genesis.body_of
        with mock.patch.object(genesis, 'station_scene', return_value=cls.old_scene), \
                mock.patch.object(genesis, 'body_of', side_effect=lambda name: legacy if name == 'station' else body_of(name)):
            made = genesis.gas_station(cls.town.client, OPENER)
        assert all(m['status'] in ('created', 'admitted') for m in made), made
        n = iter(range(100))

        def turn(who, obj, method, argument=record()):
            got = cls.town.send(op='world-turn', principal=who, object=obj, method=method,
                                argument=argument, identity=f'old-station-{next(n)}')
            assert got['status'] == 'admitted', got
            return got

        for who in (READER, OTHER):
            cls.town.send(op='world-arrive', principal='transport', did=who, handle=who.rsplit(':', 1)[1])
            turn(who, 'station', 'enter')
            turn(who, 'station', 'choose', record(choice=label('Push the door')))
            turn(OPENER, 'station', 'remember', record(who=label(who)))
        turn(READER, 'station', 'choose', record(choice=label('Take a coffee')))
        turn(READER, 'station', 'choose', record(choice=label('Wind the wall clock')))
        turn(READER, 'station', 'choose', record(choice=label('Back to the counter')))
        turn(OTHER, 'station', 'choose', record(choice=label('Listen to the radio')))
        turn(OTHER, 'station', 'choose', record(choice=label('Turn the radio off')))
        for _ in range(16):
            cls.town.send(op='world-deliver', principal='transport', limit=64)
            if not cls.town.send(op='world-pending').get('count'):
                break
        rec = cls.town.send(op='world-object', principal=OPENER, object='station')['record']
        clauses = rec['law'].splitlines()
        [methods] = [line for line in clauses if line.startswith('law methods ')]
        # The owner's clause follows the scene rules and keeps the methods law's proposal guard.
        cls.owner_clause = re.sub(r'^law methods "[^"]*": ', OWNER_CLAUSE_HEAD, methods, count=1)
        assert cls.owner_clause.startswith(OWNER_CLAUSE_HEAD), methods
        fixture_law = '\n'.join(line for line in clauses if line != methods) + '\n' + cls.owner_clause
        amended = cls.town.send(op='world-amend', principal=OPENER, object='station', version=int(rec['version']),
                               identity='owner-station-law', law=fixture_law)
        assert amended['status'] == 'admitted', amended
        cls.before = state(cls.town)
        assert scene_stamp(cls.before) is None
        assert field(cls.before, 'vars')['items'] and rows(field(cls.before, 'mine'))
        cls.register_before = state(cls.town, 'station/register')
        cls.avatars_before = {who: state(cls.town, who) for who in (READER, OTHER)}
        assert cls.town.send(op='world-snapshot')['status'] == 'snapshot'
        cls.town.close()

    def setUp(self):
        self.references = iter(range(100))
        self.directory = tempfile.TemporaryDirectory(dir=self.tmp.name)
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, 'carried.journal')
        carried = subprocess.run([binary(), 'carry', '--from', self.town.journal, '--out', self.path,
                                  '--reason', 'the shipped station scene', '--library', str(LIBRARY), *body_args(LIBRARY)],
                                 capture_output=True, text=True, timeout=600)
        self.assertEqual(carried.returncode, 0, carried.stderr)
        outcome = json.loads(carried.stdout)
        self.assertEqual(outcome['left'], [], outcome)
        moved = {row['object']: row for row in outcome['moved']}
        self.assertTrue(moved['station']['body'], moved)
        self.assertTrue(moved['kind/station']['body'], moved)
        self.host = HostProcess(binary(), self.path)
        self.addCleanup(self.host.close)
        self.assertEqual(state(self.host), self.before)
        inspected = self.host.send(op='world-inspect', principal=OPENER, object='station', source=False)
        self.assertIn('restitch', inspected['offered'], inspected)

    def refresh(self, scene=None):
        with mock.patch.object(genesis, 'station_scene', return_value=scene or self.shipped_scene):
            result = genesis.refresh(self.host, OPENER, genesis.ancestry(self.path), station=True)
        self.assertTrue(all(r['status'] in ('current', 'refreshed', 'left') for r in result), result)
        [scene_row] = [r for r in result if r['object'] == 'station' and r.get('slot') == 'scene']
        return scene_row

    def assert_scene(self, scene):
        with mock.patch.object(genesis, 'station_scene', return_value=scene):
            wings = genesis.station_wings()
        expected_rules = []
        for wing in wings:
            expected = run_pure('Spween', 'rules', label(wing), probe=SCENE_PROBE, limits={'ticks': '1000000'})
            self.assertEqual(expected['status'], 'finished', expected)
            rules = expected['value']['value']
            self.assertFalse(rules.startswith('refused:'), rules)
            expected_rules.append(rules)
        # A fresh stitch supplies the scene fields against which the replacement is compared.
        reference = f'station-reference-{next(self.references)}'
        placed = genesis.said(self.host, OPENER, 'kind/station', 'place', [('id', reference), ('name', 'A reference station')],
                              f'{reference}-place', reference)['reply']
        self.assertEqual(placed['status'], 'admitted', placed)
        for k, wing in enumerate(wings, 1):
            stitched = self.host.send(op='world-turn', principal=OPENER, object=reference, method='stitch',
                                      identity=f'{reference}-wing-{k}', argument=record(spween=label(wing)))
            self.assertEqual(stitched['status'], 'admitted', stitched)
        expected_scene = state(self.host, reference)
        st = state(self.host)
        for name in ('passages', 'start', 'cooldown', 'requires'):
            self.assertEqual(field(st, name), field(expected_scene, name), name)
        self.assertEqual(scene_stamp(st), genesis.station_digest(wings))
        actual = law(self.host)
        scene_rules = [line for line in actual.splitlines() if line.startswith('rule ')]
        self.assertEqual('\n'.join(scene_rules), ''.join(expected_rules).lstrip('\n'))
        names = re.findall(r'^rule (\w+)', actual, re.M)
        self.assertEqual(len(names), len(set(names)), actual)
        self.assertIn(self.owner_clause, actual.splitlines())

    def assert_readers(self, before=None):
        after = state(self.host)
        for name in ('vars', 'mine', 'presence', 'left', 'cites', 'things', 'tended', 'chose'):
            self.assertEqual(field(after, name), field(before or self.before, name), name)
        self.assertEqual(state(self.host, 'station/register'), self.register_before)
        for who, avatar in self.avatars_before.items():
            self.assertEqual(state(self.host, who), avatar)

    def test_carried_old_scene_is_live_after_refresh_with_vars_mine_presence_and_owner_clauses(self):
        self.assertEqual(self.refresh()['status'], 'refreshed')
        self.assert_scene(self.shipped_scene)
        self.assert_readers()
        card = self.host.send(op='world-card', principal=READER, object='station')['text']
        self.assertIn('You took the coffee', card)
        entries = [e for e in journal.entries(self.path) if (e.get('identity') or {}).get('intent', '').startswith('refresh-station-restitch-')]
        self.assertEqual(len(entries), len(genesis.station_wings()))
        self.assertTrue(all(e['identity']['principal'] == OPENER for e in entries), entries)
        self.assertTrue(any(e['outcome'].get('amendments') for e in entries), entries)
        kept = self.host.send(op='world-turn', principal=READER, object='station/register', method='inspirit',
                              identity='keep-carried-register', argument=record(surrounding=label('a ledger with no hour')))
        self.assertEqual(kept['status'], 'admitted', kept)
        left = self.host.send(op='world-turn', principal=OTHER, object='station', method='leave',
                              identity='leave-carried-station', argument=record())
        self.assertEqual(left['status'], 'admitted', left)
        wants = self.host.send(op='world-wants', principal=OPENER, object='station')['rows']
        self.assertIn('register', [w['name'] for w in wants], wants)

    def test_newly_stitched_shipped_text_is_current_without_a_restitch(self):
        town = Town(os.path.join(self.directory.name, 'new'), cleanup=self.addCleanup, furnished=False)
        made = genesis.gas_station(town.client, OPENER)
        self.assertTrue(all(m['status'] in ('created', 'admitted') for m in made), made)
        self.assertEqual(scene_stamp(state(town)), genesis.station_digest(genesis.station_wings()))
        height = town.send(op='world-status')['height']
        result = genesis.refresh(town.client, OPENER, genesis.ancestry(town.journal), station=True)
        self.assertEqual({r['status'] for r in result}, {'current'}, result)
        self.assertEqual(town.send(op='world-status')['height'], height)

    def test_refresh_installation_calls_inhabitants_once(self):
        town = Town(os.path.join(self.directory.name, 'new'), cleanup=self.addCleanup, furnished=False)
        with mock.patch.object(genesis, 'inhabitants', wraps=genesis.inhabitants) as inhabited:
            result = genesis.refresh(town.client, OPENER, genesis.ancestry(town.journal), station=True)
        self.assertTrue(all(r['status'] in ('current', 'refreshed') for r in result), result)
        inhabited.assert_called_once_with(town.client, OPENER, 'refresh')

    def test_refresh_twice_is_current_and_A_B_A_applies_A_again(self):
        self.assertEqual(self.refresh()['status'], 'refreshed')
        height = self.host.send(op='world-status')['height']
        self.assertEqual(self.refresh()['status'], 'current')
        self.assertEqual(self.host.send(op='world-status')['height'], height)
        alternate = self.shipped_scene.replace('Past the last lamp, a gas station, lit.', 'Past the last lamp, a gas station, blue.')
        self.assertNotEqual(alternate, self.shipped_scene)
        self.assertEqual(self.refresh(alternate)['status'], 'refreshed')
        self.assert_scene(alternate)
        self.assertEqual(self.refresh()['status'], 'refreshed')
        self.assert_scene(self.shipped_scene)
        self.assert_readers()
        stamps = [e['identity']['intent'] for e in journal.entries(self.path)
                  if (e.get('identity') or {}).get('intent', '').startswith('refresh-station-restitch-')]
        self.assertEqual(len(stamps), 3 * len(genesis.station_wings()))
        self.assertEqual(len(stamps), len(set(stamps)))

    def test_removed_passage_moves_only_its_reader_to_the_new_start_preserving_draw(self):
        scene = re.sub(r'(?ms)^=== off\n.*?(?=^=== |^// wing |\Z)', '', self.shipped_scene).replace('-> off\n', '-> forecourt\n')
        self.assertNotEqual(scene, self.shipped_scene)
        self.assertEqual(self.refresh(scene)['status'], 'refreshed')
        expected = copy.deepcopy(self.before)
        moved = 0
        for me in rows(field(expected, 'presence')):
            if field(me, 'at')['value'] == 'off':
                field(me, 'at')['value'] = 'forecourt'
                moved += 1
        self.assertEqual(moved, 1)
        self.assert_readers(expected)
        self.assert_scene(scene)

    def test_non_owner_and_unreadable_guard_cannot_replace_the_scene(self):
        before, before_law = state(self.host), law(self.host)
        refused = self.host.send(op='world-turn', principal=READER, object='station', method='restitch', identity='stranger-restitch',
                                 argument=record(spween=label('=== forecourt\nA stranger.\n'), part=nat(1), wings=nat(1)))
        self.assertEqual(cast_refusal(refused)[0], 'notOwner')
        self.assertEqual((state(self.host), law(self.host)), (before, before_law))
        bad = '=== forecourt\nA start.\n* [Try] { count(new.presence) >> 1 } -> forecourt\n'
        refused = self.host.send(op='world-turn', principal=OPENER, object='station', method='restitch', identity='bad-guard-restitch',
                                 argument=record(spween=label(bad), part=nat(1), wings=nat(1)))
        self.assertEqual(cast_refusal(refused)[0], 'spween')
        self.assertEqual((state(self.host), law(self.host)), (before, before_law))

    def test_maximum_wing_length_and_full_presence_keep_reader_draws(self):
        n = 0
        while len(rows(field(state(self.host), 'presence'))) < 32:
            entered = self.host.send(op='world-turn', principal=f'did:plc:restitch-full-{n}', object='station', method='enter',
                                     identity=f'full-station-{n}', argument=record())
            self.assertEqual(entered['status'], 'admitted', entered)
            n += 1
        before = state(self.host)
        wing = '=== forecourt\nA start.\n// '
        wing += 'x' * (8192 - len(wing))
        self.assertEqual(len(wing), 8192)
        replaced = self.host.send(op='world-turn', principal=OPENER, object='station', method='restitch', identity='max-wing-restitch',
                                  argument=record(spween=label(wing), part=nat(1), wings=nat(1)))
        self.assertEqual(replaced['status'], 'admitted', replaced)
        after = state(self.host)
        self.assertEqual(scene_stamp(after), genesis.station_digest([wing]))
        for name in ('vars', 'mine'):
            self.assertEqual(field(after, name), field(before, name))
        expected = copy.deepcopy(rows(field(before, 'presence')))
        for me in expected:
            field(me, 'at')['value'] = 'forecourt'
        self.assertEqual(rows(field(after, 'presence')), expected)
        self.assertNotIn('request.method == "choose"', law(self.host))
        self.assertIn(self.owner_clause, law(self.host).splitlines())

    def test_interrupted_restitch_restarts_and_keeps_readers_in_later_wings(self):
        send = self.host.send
        stopped = False

        def interrupt(request=None, **fields):
            nonlocal stopped
            req = {**(request or {}), **fields}
            if req.get('method') == 'restitch' and field(req['argument'], 'part') == nat(2) and not stopped:
                stopped = True
                return {'status': 'refused', 'reading': 'the second wing was interrupted'}
            return send(req)

        with mock.patch.object(self.host, 'send', side_effect=interrupt):
            result = genesis.refresh(self.host, OPENER, genesis.ancestry(self.path), station=True)
        [failure] = [r for r in result if r['object'] == 'station' and r.get('slot') == 'scene']
        self.assertEqual(failure['status'], 'refused', result)
        self.assertEqual(field(state(self.host), 'presence'), field(self.before, 'presence'))
        self.assertEqual(self.refresh()['status'], 'refreshed')
        self.assert_scene(self.shipped_scene)
        self.assert_readers()
        self.assertEqual(self.refresh()['status'], 'current')


if __name__ == '__main__':
    unittest.main()
