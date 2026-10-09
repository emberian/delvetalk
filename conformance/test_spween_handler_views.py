"""Generated Bend handlers drive one retained menu for town posts and the portal.

No availability is computed here: all views and turns run on the native receiver.
Only publication lookup is a local fixture; nothing is posted externally.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
import history
import portal
import town_cards
from scene import handlers, projection

FIXTURE = ROOT / 'protocols/spween-handler-workshop'
ISSUER, ACTOR, OTHER = ['did:plc:' + letter * 24 for letter in 'abc']
MEND = 'Mend the brass moth'
RELEASE = 'Release the brass moth'
REJECT = 'Try the impossible hinge'


class SpweenHandlerViews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = (FIXTURE / 'moth.scene').read_text()
        cls.handler = (FIXTURE / 'Handler.obend').read_text()
        cls.built = handlers.compile_source(cls.scene, cls.handler)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.db = self.directory / 'world.json'
        self.runtime = history.runtime('compiled')
        initialized = self.call({'op': 'messages-init', 'lineage': 'handler-views',
            'pendingLimit': 8, 'principal': ACTOR, 'intent': 'messages'})
        self.assertEqual(initialized['kind'], 'committed', initialized)
        made = self.call({'op': 'create', 'object': 'workshop', 'principal': ACTOR,
            'intent': 'create', 'protocol': self.built['protocol'], 'law': [ACTOR, OTHER]})
        self.assertEqual(made['kind'], 'committed', made)
        self.current = made['data']['root']
        (self.directory / 'manifest.json').write_text(json.dumps({'runtime': self.runtime}))
        self.app = portal.Portal(self.directory)
        self.book = town_cards.CardBook.create(self.directory / 'cards', issuer_did=ISSUER,
            world_id='urn:test:handler-views', runtime=self.runtime)
        self.serial = 0

    def call(self, request):
        return projection.world.exchange(self.db, request, profile='compiled')

    def turn(self, command, data, *, principal=ACTOR, expected=None):
        self.serial += 1
        reply = self.call({'op': 'invoke', 'object': 'workshop', 'principal': principal,
            'intent': 'turn-' + str(self.serial), 'expected': expected or self.current,
            'command': command, 'input': data})
        if reply['kind'] == 'committed':
            self.current = reply['data']['root']
        return reply

    def capture(self, alias):
        before = self.db.read_bytes()
        view = projection.project(self.current, 'workshop', expected_runtime=self.runtime)
        town = self.book.capture(view, alias)
        browser = self.app.object('workshop')
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual(town['card']['prose'], browser['prose'])
        # Portal adds its own retained-card token; action semantics stay identical.
        self.assertEqual(town['card']['actions'],
            [{key: value for key, value in action.items() if key != 'token'}
             for action in browser['actions']])
        self.assertEqual(town['card']['title'], browser['title'])
        self.assertEqual(projection.children(view), browser['children'])
        self.assertEqual(browser['children'], [])  # No invented catalogue from inventory.
        self.assertNotIn('DataWire', town['body'])
        self.assertNotIn('sourcePackages', town['body'])
        self.assertNotIn('choice:', town['body'])  # Authored choices bind this input.
        return town, browser

    @staticmethod
    def labels(card):
        return [action['label'] for action in card['actions']]

    def test_handler_state_changes_shared_offers_and_literal_spell_binds_same_action(self):
        initial, browser = self.capture('sleeping')
        self.assertEqual(self.labels(browser), ['Start'])
        self.assertEqual(self.turn('start', {})['kind'], 'committed')
        bench, browser = self.capture('bench')
        self.assertEqual(self.labels(browser), [MEND, REJECT])
        self.assertNotIn(RELEASE, bench['body'])
        self.assertIn('describe your intention for us to interpret', bench['body'])
        mend = browser['actions'][0]
        self.assertEqual(mend['fields'], [])
        prepared = self.app.prepare({'card': browser['card'], 'action': mend['id']})
        self.assertEqual(prepared['wire']['input'], {'choice': 0})
        publication = {'uri': f'at://{ISSUER}/{town_cards.FEED}/bench', 'cid': 'bench-cid'}
        value = {'$type': town_cards.FEED, 'text': bench['body']}
        def fetch(uri, cid):
            self.assertEqual((uri, cid), (publication['uri'], publication['cid']))
            return copy.deepcopy(value)
        self.book.bind('bench', publication, fetch)
        spell = town_cards.spell('bench', mend, {},
            selector=town_cards.action_word(mend, browser['actions']))
        self.assertNotIn('{', spell)  # Literal offered word; no JSON payload to author.
        record = {'$type': town_cards.FEED, 'text': spell,
                  'reply': {'root': publication, 'parent': publication}}
        source = {'uri': f'at://{ACTOR}/{town_cards.FEED}/mend', 'cid': 'mend-cid',
                  'author': ACTOR, 'pds': 'https://pds.delve.town'}
        wire, _ = self.book.resolve(record, ACTOR, source, fetch, [ISSUER])
        self.assertEqual(wire, prepared['wire'])
        committed = self.call({**wire, 'principal': ACTOR, 'intent': source['uri']})
        self.assertEqual(committed['kind'], 'committed', committed)
        self.current = committed['data']['root']
        repaired, after = self.capture('repaired')
        self.assertEqual(self.labels(after), [RELEASE, REJECT])
        self.assertNotIn(MEND, repaired['body'])
        self.assertEqual(self.book.card('bench')['view'], bench['view'])
        self.assertEqual(self.app.card(browser['card']), browser)
        self.assertEqual(self.turn('choose', {'choice': 1}, principal=OTHER)['kind'], 'committed')
        garden, after = self.capture('garden')
        self.assertEqual(self.labels(after), ['Return to the workbench'])
        self.assertIn('constellation', after['prose'])
        self.assertEqual(self.turn('choose', {'choice': 0})['kind'], 'committed')
        _, returned = self.capture('returned')
        self.assertEqual(self.labels(returned), [MEND, REJECT])

    def test_refused_stale_and_unauthorized_calls_preserve_current_view(self):
        self.assertEqual(self.turn('start', {})['kind'], 'committed')
        before, _ = self.capture('before')
        root = copy.deepcopy(self.current)
        for data, principal in [({'choice': 1}, ACTOR), ({'choice': 2}, ACTOR),
                                ({'choice': 0}, 'not-in-current-law')]:
            reply = self.turn('choose', data, principal=principal)
            self.assertNotEqual(reply['kind'], 'committed', reply)
            self.assertEqual(self.current, root)
            self.assertEqual(projection.world.wire_loads(self.db.read_text())['objects']['workshop'], root)
            view = projection.project(self.current, 'workshop', expected_runtime=self.runtime)
            self.assertEqual(view['data'], before['view']['data'])
            self.assertEqual(view['root'], root)
        self.assertEqual(self.turn('choose', {'choice': 0})['kind'], 'committed')
        repaired = copy.deepcopy(self.current)
        reply = self.turn('choose', {'choice': 2}, expected=root)
        self.assertEqual(reply['data'], 'stale read root')
        self.assertEqual(self.current, repaired)
        _, after = self.capture('after-stale')
        self.assertEqual(self.labels(after), [RELEASE, REJECT])

    def test_exact_authored_sources_and_revision_remain_inspectable(self):
        self.assertEqual(self.turn('start', {})['kind'], 'committed')
        old, browser = self.capture('old-score')
        detail = self.app.detail(browser['card'])
        source = detail['source']
        self.assertEqual(source['spweenSource']['source'], self.scene)
        self.assertEqual(source['spweenSource'], self.current['protocol']['spweenSource'])
        self.assertEqual(source['sourcePackages'], self.current['protocol']['sourcePackages'])
        modules = next(iter(source['sourcePackages'].values()))['modules']
        self.assertEqual(next(m['source'] for m in modules if m['name'] == 'Handler'), self.handler)
        self.assertEqual(source['program'], self.current['protocol']['viewProgram'])
        revised_scene = self.scene.replace('A moth of folded brass waits', 'A silver moth waits')
        revised = handlers.compile_source(revised_scene, self.handler)['protocol']
        reply = self.call({'op': 'reprogram', 'object': 'workshop', 'principal': ACTOR,
            'intent': 'revise-score', 'expected': self.current, 'protocol': revised,
            'state': self.current['state']})
        self.assertEqual(reply['kind'], 'committed', reply)
        self.current = reply['data']['root']
        _, current = self.capture('new-score')
        self.assertIn('A silver moth waits', current['prose'])
        self.assertEqual(self.labels(current), self.labels(browser))
        self.assertEqual(self.app.detail(browser['card']), detail)
        self.assertEqual(self.book.card('old-score')['view'], old['view'])
        stale = town_cards.affordances.request(old['view'], 'a1', ACTOR, 'old-score-call', {})
        self.assertEqual(self.call(stale)['data'], 'stale read root')


if __name__ == '__main__':
    unittest.main()
