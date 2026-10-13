"""An open town's own genesis (`deploy.genesis --profile open`; docs/DEPLOY.md "A second instance"): the frame, the porch
with its three bells, the all-night station with its inhabitants, the town's register (its own, empty) and its desk,
the library with a guide that carries the open door at the town's own origin, the page for one who arrives cold and the
town's first line pointing there, the config's limits for newcomers; no door's page published, since nothing of it is
posted on delve.town. The town's own genesis is unchanged.

Evidence for docs/DEPLOY.md "A second instance" (layer: objects). Refuted by a missing place, a register another hand
holds or with a row, a guide naming another origin or without its door, a page published for delve.town, a first line
not the town's, the limits not the config's, or an open profile run over a config that says invited.
"""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr

from deploy import genesis
from tests.host import served
from transport.config import LIBRARY, Config
from transport.host import HostClient, door_rows, plain
from transport.mirror import library_pages

ORIGIN = 'https://obend.example'
OPENER = 'did:web:obend.example'


class OpenGenesis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.config = Config(origin=ORIGIN, arrival='open', turn_quota=40, object_quota=12, paint_budget=200, hob_budget=150)
        cls.server = served(os.path.join(cls.tmp.name, 'state'), cleanup=cls.addClassCleanup, opener=OPENER, library=LIBRARY)
        cls.root = HostClient(cls.server.root)
        cls.addClassCleanup(cls.root.close)
        cls.made, cls.refusal = genesis.open_town(cls.root, OPENER, cls.config)

    def view(self, obj):
        v = self.root.send({'op': 'world-view', 'principal': OPENER, 'object': obj})
        self.assertEqual(v['status'], 'viewed', (obj, v))
        return v

    def test_it_runs_whole_and_makes_the_places_an_open_town_has(self):
        self.assertIsNone(self.refusal)
        self.assertTrue(all(m['status'] in ('created', 'admitted') for m in self.made), [m for m in self.made if m['status'] not in ('created', 'admitted')])
        have = set(genesis.existing(self.root, OPENER))
        for obj in ('commonplace', 'policy', 'tide', 'workshop', 'kinds', 'library', 'porch', 'bell/1', 'bell/2', 'bell/green',
                    'station', 'station/register', 'station/regular', 'station/dj', 'station/bee', 'station/parlour', 'station/parlour/planchette', 'kind/register', 'register',
                    'register/desk', 'weather', 'porch/lamp'):
            self.assertIn(obj, have)
        porch = {d['to']['object'] for d in door_rows(self.view('porch'))}
        self.assertTrue({'bell/1', 'bell/2', 'bell/green', 'station'} <= porch, porch)

    def test_the_register_is_the_towns_and_empty(self):
        state = plain(self.view('register')['state'])
        self.assertEqual((state['owner'], state['lines']['items']), (OPENER, []))
        self.assertIn('register', {d['to']['object'] for d in door_rows(self.view('commonplace'))})

    def test_the_guide_names_this_town_and_its_door_and_the_arrive_page_is_shelved(self):
        pages = {p['name']: p for p in library_pages(self.root, OPENER)}
        self.assertEqual(pages['arrive']['body'], genesis.page_body('arrive'))
        guide = ' '.join(pages[f'guide-{k}']['body'] for k in range(1, 40) if f'guide-{k}' in pages)
        self.assertIn("This town's door is open: ask it for a key.", guide)
        self.assertIn(ORIGIN + '/enter', guide)
        self.assertNotIn('gsb.fg-goose.online', guide)
        studio = next(d for d in plain(self.view('commonplace')['state'])['cites'] if d['label'] == 'STUDIO')
        self.assertIn(ORIGIN + '/AGENTS.md', studio['description'])

    def test_the_towns_first_line_points_at_the_arrive_page_and_no_page_was_published(self):
        lines = plain(self.view('commonplace')['state'])['lines']['items']
        self.assertEqual(lines[0]['text'], genesis.OPEN_LINE, lines)
        self.assertIn("Postmark's residents are the first invited.", genesis.OPEN_LINE)
        self.assertFalse(any('page' in m for m in self.made))
        self.assertEqual(self.root.send({'op': 'world-publications', 'principal': 'clock', 'after': 0}).get('publications') or [], [])

    def test_the_limits_are_the_configs(self):
        status = self.root.send({'op': 'world-status', 'principal': 'guest:obend.example:kim'})
        self.assertEqual((status['turnQuota'], status['objectQuota'], status['paintQuota']['quota'], status['modelQuota']['quota']),
                         (40, 12, 200, 150))

    def test_an_open_profile_over_an_invited_config_is_refused(self):
        with tempfile.TemporaryDirectory() as towns, redirect_stderr(io.StringIO()) as err:
            code = genesis.main(['--root-socket', self.server.root, '--towns', towns, '--profile', 'open'])
        self.assertEqual(code, 64)
        self.assertIn('arrival is invited', err.getvalue())


if __name__ == '__main__':
    unittest.main()
