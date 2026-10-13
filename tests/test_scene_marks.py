"""Scene stamps stay internal on fresh and carried/refreshed station cards.

Refuted by a station-scene digest in Strokes JSON/text, a mark fact's expansion,
the painter's request, a telling's exact lines, or a rendered card; or by a
presentation read changing the row used by genesis's chained-digest refresh.
Run against the current host: python3 -m unittest tests.test_scene_marks -v
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deploy import genesis
from tests.host import binary
from tests.test_properties import HASH
from tests.town import Town
from tests.wire import field, label, nat, record, relation, rows
from transport.carry import body_args
from transport.config import LIBRARY
from transport.host import HostProcess

OPENER = genesis.OPENER
READER = 'did:plc:scene-reader'


def scene_marks(host):
    state = host.send(op='world-view', principal=OPENER, object='station')['state']
    return [m for m in rows(field(state, 'marks'))
            if field(m, 'name')['value'].startswith('station-scene-')]


class SceneMarks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'DELVETALK_RENDER_CACHE': str(Path(self.tmp.name, 'renders'))})
        env.start()
        self.addCleanup(env.stop)

    def station(self, *, old=False):
        town = Town(os.path.join(self.tmp.name, 'old' if old else 'fresh'),
                    cleanup=self.addCleanup, furnished=False)
        scene, body_of = genesis.station_scene(), genesis.body_of
        # A distinct old package forces the carry's body replacement. Its four-field
        # marks have exactly the historical digest-named row shape, without metadata.
        with patch.object(genesis, 'station_scene', return_value=scene + ('\n// old scene\n' if old else '')), \
                patch.object(genesis, 'body_of', side_effect=lambda name: body_of(name) +
                             ('\n# old station body\n' if old and name == 'station' else '')):
            made = genesis.gas_station(town.client, OPENER)
        self.assertTrue(all(m['status'] in ('created', 'admitted') for m in made), made)
        return town

    def assert_surfaces(self, host):
        before = scene_marks(host)
        self.assertTrue(before)
        self.assertTrue(all(HASH.search(field(m, 'name')['value']) for m in before))
        card = host.send(op='world-card', principal=READER, object='station')
        self.assertEqual(card['status'], 'card', card)
        self.assertIsNone(HASH.search(card['text']), card['text'])
        # A bare telling does not list the marks: the stitch's amend step makes its write
        # unreadable to the telling's span (spanOf), so it is only checked for the digest.
        told = host.send(op='world-strokes', principal=READER, object='station', telling={})
        self.assertEqual(told['status'], 'strokes', told)
        self.assertIsNone(HASH.search(json.dumps(told)), told)
        for more in ({},):
            with self.subTest(surface=more):
                got = host.send(op='world-strokes', principal=READER, object='station', **more)
                self.assertEqual(got['status'], 'strokes', got)
                strokes = got['strokes']
                self.assertTrue(strokes['marks'], strokes)
                self.assertEqual({m['name'] for m in strokes['marks']}, {'the scene'})
                self.assertIsNone(HASH.search(got['text']), got['text'])
                self.assertIsNone(HASH.search(json.dumps(strokes)), strokes)
                facts = [f for f in strokes['facts'] if f['kind'] == 'mark']
                self.assertTrue(facts, strokes)
                self.assertEqual({f['value'] for f in facts}, {'the scene'})
                self.assertEqual({f['clause'] for f in facts}, {'it bears the mark "the scene"'})
                checked = host.send(op='world-render-check', principal=READER, object='station',
                                    text='[[' + ','.join(str(f['id']) for f in facts[:5]) + ']]', **more)
                self.assertEqual(checked['status'], 'verified', checked)
                self.assertIsNone(HASH.search(checked['text']), checked)
                # Exercise the request built from Strokes.text and the cached card.
                host.send(op='world-renders')
                rendered = host.send(op='world-render', principal=READER, object='station', **more)
                self.assertEqual(rendered['status'], 'pending', rendered)
                pending = host.send(op='world-renders')['pending']
                request = next(p['request'] for p in pending if p['key'] == rendered['key'])
                self.assertIsNone(HASH.search(request['user']), request['user'])
                submitted = host.send(op='world-render-submit', key=rendered['key'],
                                      reply={'status': 'replied', 'raw': f"[[{facts[0]['id']}]]",
                                             'model': 'claude-haiku-5-5', 'usage': {}})
                self.assertEqual(submitted['status'], 'painted', submitted)
                painted = host.send(op='world-render', principal=READER, object='station', **more)
                self.assertEqual(painted['status'], 'painted', painted)
                self.assertIn('it bears the mark "the scene"', painted['text'])
                self.assertIsNone(HASH.search(painted['text']), painted['text'])
                if more:
                    self.assertIsNone(HASH.search(json.dumps(painted['telling'])), painted['telling'])
        self.assertEqual(scene_marks(host), before)

    def test_genesis_station_after_writing_its_scene_shows_short_marks(self):
        town = self.station()
        self.assert_surfaces(town)
        marks = scene_marks(town)
        latest = max(marks, key=lambda m: int(field(m, 'at')['value']))
        self.assertEqual(field(latest, 'name')['value'][14:78], genesis.station_digest(genesis.station_wings()))
        self.assertEqual(genesis.station_restitch(town.client, OPENER)['status'], 'current')

    def test_carried_station_keeps_old_rows_and_shows_short_marks_after_refresh(self):
        town = self.station(old=True)
        old_marks = scene_marks(town)
        self.assertEqual(town.send(op='world-snapshot')['status'], 'snapshot')
        town.close()
        path = str(Path(self.tmp.name, 'carried.journal'))
        carried = subprocess.run([binary(), 'carry', '--from', town.journal, '--out', path,
                                  '--reason', 'scene mark presentation regression', '--library', str(LIBRARY),
                                  *body_args(LIBRARY)], capture_output=True, text=True, timeout=600)
        self.assertEqual(carried.returncode, 0, carried.stderr)
        report = json.loads(carried.stdout)
        self.assertEqual(report['left'], [], report)
        self.assertIn('station', {m['object'] for m in report['moved']}, report)
        host = HostProcess(binary(), path)
        self.addCleanup(host.close)
        self.assertEqual(scene_marks(host), old_marks)
        # Even before refresh the old names need to be safe on current cards.
        got = host.send(op='world-strokes', principal=READER, object='station')
        self.assertEqual({m['name'] for m in got['strokes']['marks']}, {'the scene'})
        refreshed = genesis.refresh(host, OPENER, genesis.ancestry(path), station=True)
        self.assertTrue(all(r['status'] in ('current', 'refreshed', 'left') for r in refreshed), refreshed)
        self.assertIn({'object': 'station', 'slot': 'scene', 'status': 'refreshed',
                       'reading': 'the scene text changed'}, refreshed)
        self.assertTrue(all(m in scene_marks(host) for m in old_marks))
        self.assert_surfaces(host)
        self.assertEqual(genesis.station_restitch(host, OPENER)['status'], 'current')

    def test_maximum_wing_and_expanded_budget_keep_the_digest_internal(self):
        town = self.station()
        wing = '=== forecourt\nA start.\n// '
        wing += 'x' * (8192 - len(wing))
        written = town.send(op='world-turn', principal=OPENER, object='station', method='restitch',
                            identity='maximum-scene-mark',
                            argument=record(spween=label(wing), part=nat(1), wings=nat(1)))
        self.assertEqual(written['status'], 'admitted', written)
        self.assert_surfaces(town)
        got = town.send(op='world-strokes', principal=READER, object='station')['strokes']
        fact = next(f for f in got['facts'] if f['kind'] == 'mark')
        count = (got['limit'] + 1) // (len(fact['clause']) + 2)
        for n, expected in ((count, 'verified'), (count + 1, 'rejected')):
            checked = town.send(op='world-render-check', principal=READER, object='station',
                                text='[[' + ','.join([str(fact['id'])] * n) + ']]')
            self.assertEqual(checked['status'], expected, checked)
            if expected == 'rejected':
                self.assertEqual(checked['clause'], 'length', checked)
                self.assertIn('expanded', checked['detail'])

    def test_mark_projection_uses_the_prefix_on_any_object_and_keeps_other_names(self):
        town = Town(os.path.join(self.tmp.name, 'probe'), cleanup=self.addCleanup, furnished=False)
        source = '''edition ObjectiveBend 1
import ./List.obend as Lists
import ./Relation.obend as Relations
import ./Rows.obend as Rows
record State:
  marks: Relations.Relation<Rows.Mark>
def initial() -> State:
  {marks: Relations.empty()}
def relations() -> Relations.Decls:
  Relations.Decls.cons({head: {field: "marks", key: Lists.List.cons({head: "name", tail: Lists.List.nil()}), limit: 0n}, tail: Relations.Decls.nil()})
'''
        names = ['rung', 'station-scene-not-a-digest', 'station-scenes-remembered', 'm' * 128]
        seed = record(marks=relation(*(record(name=label(name), who=label(OPENER),
                                             handle=label(''), at=nat(1)) for name in names)))
        made = town.send(op='world-create', principal=OPENER, object='mark-probe', identity='mark-probe',
                         source=source, entry='initial', seed=seed)
        self.assertEqual(made['status'], 'created', made)
        got = town.send(op='world-strokes', principal=READER, object='mark-probe')
        self.assertEqual({m['name'] for m in got['strokes']['marks']},
                         {'rung', 'the scene', 'station-scenes-remembered', 'm' * 128})
        self.assertIn('it has rung', [f['clause'] for f in got['strokes']['facts']])
        self.assertNotIn('station-scene-not-a-digest', got['text'])
        held = town.send(op='world-view', principal=OPENER, object='mark-probe')['state']
        self.assertEqual({field(m, 'name')['value'] for m in rows(field(held, 'marks'))}, set(names))
